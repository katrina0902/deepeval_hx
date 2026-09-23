"""两层指标加载：大类 YAML + 任务 YAML → 指标列表。

大类 YAML（categories/<大类>.yaml）：
    meta:       test_case 字段约定 / evaluate 参数
    metrics:    大类通用指标
任务 YAML（categories/<大类>/<任务>.yaml）：
    meta:       任务级补充（可覆盖）
    metrics:    任务专属指标（与大类合并，同名 key 任务优先）

指标类型（metrics.<key>.metric）：
    geval | json_correctness | summarization | pattern_match |
    answer_relevancy | faithfulness

参数化输入/输出（外部导出 CSV 的 JSON 列）：
    任务 YAML 的 meta.input_template 用 {参数名} 引用 input_text JSON 内字段，
    指标条目的 retrieval_fields / output_field 按指标定制素材与被评输出：
      retrieval_fields: [case_info, current_mediation_record]  # 素材字段
      output_field: key_communication_facts.meditation_levers  # ai_response JSON 子字段
"""

import json
import os
import re
from typing import Any, Dict, List

import yaml

from deepeval.metrics import (
    GEval,
    JsonCorrectnessMetric,
    SummarizationMetric,
    PatternMatchMetric,
    AnswerRelevancyMetric,
    FaithfulnessMetric,
    BaseMetric,
)
from deepeval.test_case import LLMTestCase, SingleTurnParams

from tasks import EXTRA_PARAMS

_PARAM_MAP = {
    "input": SingleTurnParams.INPUT,
    "actual_output": SingleTurnParams.ACTUAL_OUTPUT,
    "expected_output": SingleTurnParams.EXPECTED_OUTPUT,
    "context": SingleTurnParams.CONTEXT,
    "retrieval_context": SingleTurnParams.RETRIEVAL_CONTEXT,
}


# ---------- 参数化渲染：{参数名} → input_text JSON 内字段 ----------

def _flatten_params(params: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    """拍平嵌套 dict：{a: {b: 1}} → {a.b: 1}（点路径取子字段用）。"""
    out: Dict[str, Any] = {}
    for k, v in params.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten_params(v, key))
        out[key] = v
    return out


def render_template(template: str, params: Dict[str, Any]) -> str:
    """把模板内 {参数名} 替换为 input_text JSON 对应字段的值（支持 a.b 点路径）。

    - 字段值是 dict/list 时序列化为 JSON 字符串（ensure_ascii=False）
    - 参数缺失（如首次生成时 existing_case_overview 不存在）渲染为空串
    """
    flat = _flatten_params(params)

    def _sub(m):
        key = m.group(1)
        v = flat.get(key)
        if v is None:
            return ""
        return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)

    return re.sub(r"\{([a-zA-Z_][\w.]*)\}", _sub, template)


def field_to_text(value: Any) -> str:
    """素材字段值 → 文本块：dict/list 转 JSON 串，str 原样，None/空 → 空串。"""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def _extract_field(container: Dict, dotted: str) -> Any:
    """按 a.b.c 点路径取 JSON 子字段；任一层缺失返回 None。"""
    cur: Any = container
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


# ---------- 指标视图包装器：按指标定制 test case 的素材与被评输出 ----------

# 评估结果/配置属性：读写都直通内层指标（报告、缓存、进度条读的都是这些）
_RESULT_ATTRS = frozenset({
    "threshold", "score", "score_breakdown", "reason", "success",
    "evaluation_model", "strict_mode", "async_mode", "verbose_mode",
    "include_reason", "error", "evaluation_cost", "input_tokens",
    "output_tokens", "verbose_logs", "skipped", "flaky",
    "model", "using_native_model", "_required_params",
})


class MetricView(BaseMetric):
    """按指标给内层指标一个"定制视图"的 test case。

    外部导出 CSV 的两列 JSON（input_text / ai_response_content）在 run_eval.py
    加载时解析，原始 JSON 挂在 test_case._eval_params（输入参数集）与
    test_case._eval_output（输出参数集）上。本包装器在 measure 前按指标配置
    重铸视图：

    - retrieval_fields: 素材字段（input_text JSON 内），拼成 retrieval_context
    - output_field:     被评输出（ai_response_content JSON 子字段，点路径）
    - input_material:   true 时素材块直接替换 input（summarization 等
                        从 input 提取基准事实的指标用；默认 False，input 保持
                        渲染后的任务模板，素材走 retrieval_context）
    - raw_input:        true 时 input 用整个 input_text 原始 JSON 串
                        （json_correctness 等以完整输入为对象的指标用）

    未配置 retrieval_fields/output_field 时原样透传（行为与直接用内层指标一致）。
    继承 BaseMetric 以通过 evaluate 的类型校验；measure 委托内层指标，
    结果属性（score/reason/...）双向直通，报告/缓存/展示与普通指标无差别。
    """

    def __init__(self, inner: BaseMetric, retrieval_fields: List[str] = None,
                 output_field: str = None, input_material: bool = False,
                 raw_input: bool = False):
        # inner 一律重建独立副本（构造式拷贝，模型引用共享，与 deepeval 的
        # copy_metrics 同语义）：deepeval 异步执行会给每个用例 copy_metrics
        # 重建包装器（type(metric)(**vars(metric))，inner 传同一引用）——若不
        # 在此拷贝，所有并发用例共享同一个内层指标对象，score/reason 会互相
        # 覆盖（报告出现"上一个 case 的指标串到下一个 case"）。每次 __init__
        # 都拷贝一次，保证每个用例的包装器各持独立 inner。
        if inner is not None:
            from deepeval.metrics.utils import copy_metrics as _copy_metrics

            inner = _copy_metrics([inner])[0]
        self.inner = inner
        self.retrieval_fields = list(retrieval_fields or [])
        self.output_field = output_field
        self.input_material = input_material
        self.raw_input = raw_input

    # ---- 属性直通：读 _RESULT_ATTRS 走内层，其余找不到再兜底 __getattr__ ----
    def __getattribute__(self, item):
        if item in _RESULT_ATTRS:
            return getattr(object.__getattribute__(self, "inner"), item)
        return object.__getattribute__(self, item)

    def __setattr__(self, item, value):
        if item in _RESULT_ATTRS:
            setattr(object.__getattribute__(self, "inner"), item, value)
        else:
            object.__setattr__(self, item, value)

    def __getattr__(self, item):
        if item == "inner":
            raise AttributeError(item)
        return getattr(self.inner, item)

    # ---- 执行：铸视图 → 调内层指标 ----
    def _cast(self, test_case: LLMTestCase) -> LLMTestCase:
        update: Dict[str, Any] = {}
        params = getattr(test_case, "_eval_params", None) or {}
        if self.raw_input:
            # 整个 input_text 原始 JSON 串作 input（含素材，retrieval_context 置空）；
            # actual_output 用输出列原始内容（含栅栏等原样），不做任何处理
            update["input"] = field_to_text(params) if params else test_case.input
            update["actual_output"] = (
                getattr(test_case, "_eval_output_raw", None)
                or test_case.actual_output
            )
            update["retrieval_context"] = None
        elif self.retrieval_fields:
            blocks = []
            for f in self.retrieval_fields:
                text = field_to_text(_extract_field(params, f))
                if text:
                    blocks.append(f"【{f}】\n{text}")
            if self.input_material:
                # summarization 类：基准事实来自 input，素材直接替换
                update["input"] = "\n\n".join(blocks)
            else:
                update["retrieval_context"] = blocks or None
        output_params = getattr(test_case, "_eval_output", None) or {}
        if self.output_field:
            picked = _extract_field(output_params, self.output_field)
            text = field_to_text(picked)
            # 空输出填占位符：deepeval 会把空 actual_output 判为缺参跳过，
            # 但业务规则是"留空为正确/错误"（criteria 内判定），须正常送评
            if not text.strip():
                text = "（空：模型该字段未输出任何内容）"
            update["actual_output"] = text
        if not update:
            self.view_params = None
            return test_case
        view = test_case.model_copy(update=update)
        # 落档：该指标实际送评的参数视图（报告按指标展示，create_metric_data 读取）
        self.view_params = {
            "input": view.input,
            "actualOutput": view.actual_output,
            "retrievalContext": view.retrieval_context,
        }
        return view

    def measure(self, test_case: LLMTestCase, *args, **kwargs):
        return self.inner.measure(self._cast(test_case), *args, **kwargs)

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs):
        return await self.inner.a_measure(self._cast(test_case), *args, **kwargs)

    @property
    def __name__(self):
        return self.inner.__name__


def attach_material_fields(test_cases: List[LLMTestCase], spec: Dict[str, Any]) -> None:
    """素材落档：各指标 retrieval_fields 的并集挂到用例的 retrieval_context。

    MetricView 铸的视图只发给 judge，用完即弃；报告/云端记录的是原始用例。
    这里把素材以并集形式补挂到原始用例上（test_run JSON 的 retrievalContext
    / Confident AI 网页 / 本地 HTML 报告即可看到 judge 依据的素材），
    不影响 MetricView 的按指标定制视图。
    """
    fields = []
    for cfg in (spec.get("metrics") or {}).values():
        for f in cfg.get("retrieval_fields") or []:
            if f not in fields:
                fields.append(f)
    if not fields:
        return
    for tc in test_cases:
        params = getattr(tc, "_eval_params", None) or {}
        blocks = [b for b in (field_to_text(_extract_field(params, f)) for f in fields) if b]
        if blocks:
            # 块名与 MetricView 素材块格式一致
            tc.retrieval_context = [f"【{f}】\n{b}" for f, b in zip(fields, blocks) if b]


def _load_yaml(path: str) -> Dict[str, Any]:
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_category_spec(category_config: str, task_criteria: str) -> Dict[str, Any]:
    """合并大类与任务两级 YAML：metrics 同名覆盖，meta 递归合并（任务优先）。"""
    cat = _load_yaml(category_config)
    task = _load_yaml(task_criteria)

    metrics = dict(cat.get("metrics") or {})
    metrics.update(task.get("metrics") or {})

    meta = dict(cat.get("meta") or {})
    for k, v in (task.get("meta") or {}).items():
        if isinstance(v, dict) and isinstance(meta.get(k), dict):
            meta[k] = {**meta[k], **v}
        else:
            meta[k] = v

    return {"meta": meta, "metrics": metrics}


# ---------- 各指标类型的构建器 ----------

def _build_geval(cfg: dict, task: str, model) -> object:
    params = [_PARAM_MAP[p] for p in cfg["evaluation_params"]]
    return GEval(
        name=cfg["name"],
        criteria=cfg["criteria"],
        evaluation_params=params,
        threshold=cfg.get("threshold", 0.5),
        model=model,
    )


# ---------- JSON Schema（YAML 内联）→ Pydantic 模型 ----------

def _schema_to_model(schema: dict, model_name: str = "ExpectedSchema"):
    """YAML 里的 JSON-Schema 风格定义 → Pydantic 模型。

    支持的字段类型：str / int / float / bool / list / dict（嵌套 object 同规则递归）。
    示例：
        schema:
          case_brief: str
          key_communication_facts:
            type: object
            fields:
              risk_items: str
    """
    from pydantic import create_model

    def _fields(props: dict, prefix: str):
        out = {}
        for fname, fdef in props.items():
            if isinstance(fdef, dict) and fdef.get("type") == "object":
                out[fname] = (_schema_to_model(fdef, f"{prefix}_{fname}"), ...)
            elif isinstance(fdef, dict) and fdef.get("type") == "list":
                out[fname] = (list, ...)
            else:
                # 允许写 "str" / str / {"type": "str"} 三种形式
                tname = fdef.get("type") if isinstance(fdef, dict) else fdef
                tname = {"string": "str", "integer": "int", "number": "float",
                         "boolean": "bool"}.get(tname, tname or "str")
                out[fname] = ({
                    "str": str, "int": int, "float": float, "bool": bool,
                }.get(tname, str), ...)
        return out

    return create_model(model_name, **_fields(schema.get("fields", schema), model_name))


def _build_json_correctness(cfg: dict, task: str, model) -> object:
    schema_def = cfg.get("schema")
    if schema_def is None:
        raise ValueError(
            f"json_correctness 需要在 YAML 指标条目下提供 schema（字段名→类型），"
            f"与 geval 维度同文件维护"
        )
    return JsonCorrectnessMetric(
        expected_schema=_schema_to_model(schema_def),
        threshold=cfg.get("threshold", 0.5),
        model=model,
    )


def _build_summarization(cfg: dict, task: str, model) -> object:
    category, task_name = task.split("/", 1)
    questions = cfg.get("assessment_questions") or (
        EXTRA_PARAMS.get(category, {}).get(task_name, {}).get("summarization_questions")
    )
    return SummarizationMetric(
        threshold=cfg.get("threshold", 0.5),
        assessment_questions=questions,
        model=model,
    )


def _build_pattern_match(cfg: dict, task: str, model) -> object:
    return PatternMatchMetric(
        pattern=cfg["pattern"],
        threshold=cfg.get("threshold", 0.5),
        ignore_case=cfg.get("ignore_case", False),
    )


def _build_answer_relevancy(cfg: dict, task: str, model) -> object:
    return AnswerRelevancyMetric(
        threshold=cfg.get("threshold", 0.5),
        model=model,
    )


def _build_faithfulness(cfg: dict, task: str, model) -> object:
    return FaithfulnessMetric(
        threshold=cfg.get("threshold", 0.5),
        model=model,
        include_reason=cfg.get("include_reason", True),
    )


_METRIC_BUILDERS = {
    "geval": _build_geval,
    "json_correctness": _build_json_correctness,
    "summarization": _build_summarization,
    "pattern_match": _build_pattern_match,
    "answer_relevancy": _build_answer_relevancy,
    "faithfulness": _build_faithfulness,
}


def build_metrics(category_config: str, task_criteria: str, task: str, model=None) -> List:
    """大类 ∪ 任务 指标（同名任务优先）→ 指标实例列表。

    配了 retrieval_fields / output_field 的指标会包一层 MetricView，
    执行时按该指标重铸 test case 视图（素材块 / 被评子字段）。
    """
    spec = load_category_spec(category_config, task_criteria)
    metrics = []
    for key, cfg in spec["metrics"].items():
        kind = cfg.get("metric", "geval")
        builder = _METRIC_BUILDERS.get(kind)
        if builder is None:
            raise ValueError(
                f"未知指标类型 '{kind}'（{key}）。可选：{list(_METRIC_BUILDERS)}"
            )
        if cfg.get("retrieval_fields") and kind == "geval":
            # GEval 只把 evaluation_params 列出的字段注入 judge prompt：
            # 配了素材字段就自动带上 retrieval_context（须在 builder 前改）
            p = cfg.setdefault("evaluation_params", ["input", "actual_output"])
            if "retrieval_context" not in p:
                p.append("retrieval_context")
        metric = builder(cfg, task, model)
        if any(cfg.get(k) for k in ("retrieval_fields", "output_field", "input_material", "raw_input")):
            metric = MetricView(
                metric,
                retrieval_fields=cfg.get("retrieval_fields"),
                output_field=cfg.get("output_field"),
                input_material=bool(cfg.get("input_material")),
                raw_input=bool(cfg.get("raw_input")),
            )
        metrics.append(metric)
    return metrics
