"""按任务运行评估（两层：大类 category / 任务 task）。

用法：
    python examples/finance_eval/run_eval.py --list             # 列出大类与任务
    python examples/finance_eval/run_eval.py                     # 运行全部任务
    python examples/finance_eval/run_eval.py --category extraction   # 运行整个大类
    python examples/finance_eval/run_eval.py --task extraction/case_summary
    python examples/finance_eval/run_eval.py --task extraction/case_summary,judgment/communication_validity
    python examples/finance_eval/run_eval.py --task extraction/case_summary --offset 100 --limit 200 #跳过前100行(不包含表头)，取200条

- 大类通用指标：examples/finance_eval/categories/<大类>.yaml（meta 里含 test_case/evaluate 约定）
- 任务专属指标：examples/finance_eval/categories/<大类>/<任务>.yaml（同名 key 覆盖大类）
- 数据：examples/finance_eval/data/<大类>/<任务>.csv，每行一次输入输出
- 业务 prompt：examples/finance_eval/prompts/<任务名>/<版本名>.md（自动取最新版）
- 模型：.env.local（仓库根，GLM_* / DOUBAO_*）
- 报告：终端明细 + 仓库根 .deepeval_results/ 下 JSON / MD / HTML
"""

import argparse
import csv
import glob
import json
import os
import re
import sys

# 仓库根目录插到 sys.path 最前：优先加载项目内 fork 的 deepeval
# （含汉化模板 deepeval/metrics/**/templates/*.txt 及其编译产物 templates.json），
# 而非 pip 安装版 site-packages。改 .txt 后重跑 scripts/compile_metric_templates.py 即生效。
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(1, os.path.dirname(os.path.abspath(__file__)))

# .env.local 固定从仓库根找（deepeval 默认按 CWD 找，从其他目录运行会失效）
os.environ.setdefault("ENV_DIR_PATH", _REPO_ROOT)

from deepeval import evaluate
from deepeval.evaluate.configs import AsyncConfig, DisplayConfig, ErrorConfig
from deepeval.test_case import LLMTestCase

from eval_config import JUDGE_MODEL, PROVIDER
from metrics_loader import (
    attach_material_fields,
    build_metrics,
    load_category_spec,
    render_template,
)
from tasks import CATEGORIES, TASKS, tasks_in_category

RESULTS_DIR = os.path.join(_REPO_ROOT, ".deepeval_results")


def _read_csv_rows(path: str) -> list:
    """读 CSV 为 dict 行列表：优先 UTF-8（含 BOM），解码失败回退 GB18030。

    外部导出的 CSV 常见两种编码（Excel 另存时 GBK 居多），逐块探测避免整表报废。
    """
    for enc in ("utf-8-sig", "gb18030"):
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("utf-8/gb18030", b"", 0, 1, f"CSV 编码无法识别: {path}")


def _strip_json_fence(text: str) -> str:
    """剥离 Markdown 代码栅栏（```json ... ```）：LLM 输出常被包裹，非坏数据。"""
    t = (text or "").strip()
    if t.startswith("```"):
        # 去首行 ``` 或 ```json，去尾部 ```
        first_nl = t.find("\n")
        if first_nl != -1:
            t = t[first_nl + 1 :]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def load_test_cases_from_csv(path: str, columns: dict = None, limit: int = None, input_template: str = None, offset: int = None) -> list:
    """CSV 每行一条用例。

    - 标准格式（data/<大类>/<任务>.csv）：列名与 LLMTestCase 字段对应。
      必需列 input, actual_output；可选 expected_output/context/
      retrieval_context/name/tags
    - 外部导出格式（tasks.py 里配了 columns 时）：按映射取列。
      columns = {ai_task: 筛选值, input: 输入列名, actual_output: 输出列名,
                 case_id: 案件列, trigger_time: 时间列, ...}
      input/actual_output 两列均为 JSON 串：解析后原始 dict 挂到
      tc._eval_params / tc._eval_output，供指标级 retrieval_fields /
      output_field 取素材与子字段；input_template（任务 YAML meta 配置）
      用 {参数名} 渲染最终 input。
    """
    rows = _read_csv_rows(path)

    if columns:
        # 外部导出格式：先按 ai_task 筛选，再映射列名
        task_filter = columns.get("ai_task")
        if task_filter:
            rows = [r for r in rows if (r.get("ai_task") or "").strip() == task_filter]
        col_in = columns.get("input", "input_text")
        col_out = columns.get("actual_output", "ai_response_content")
        col_case = columns.get("case_id")
        col_time = columns.get("trigger_time")
        col_exp = columns.get("expected_output")

        if offset:
            rows = rows[offset:]
        # 绝对行号（分批跑时保证跨批次用例名不重、--resume 匹配稳定）
        row_start = (offset or 0) + 1
        if limit:
            rows = rows[:limit]
        test_cases = []
        n_bad = 0
        for i, row in enumerate(rows, row_start):
            if not (row.get(col_in, "") or "").strip():
                continue
            # 两列 JSON 解析：失败则该行跳过（坏数据不该炸整个任务）
            try:
                params = json.loads(_strip_json_fence(row[col_in]))
                if not isinstance(params, dict):
                    raise ValueError("input_text 非对象")
                out_raw = _strip_json_fence(row.get(col_out, "") or "")
                output_params = json.loads(out_raw) if out_raw else {}
                if not isinstance(output_params, dict):
                    output_params = {}
            except (json.JSONDecodeError, ValueError):
                n_bad += 1
                continue
            # 渲染参数化 input 模板（{参数名} → input_text JSON 字段）
            rendered_input = render_template(input_template, params) if input_template else row[col_in]
            name = row.get("name") or f"case{i}"
            meta_bits = []
            if col_case and row.get(col_case):
                meta_bits.append(f"case_id={row[col_case].strip()}")
            if col_time and row.get(col_time):
                meta_bits.append(f"trigger_time={row[col_time].strip()}")
            if meta_bits:
                name = f"{name} | {' '.join(meta_bits)}"
            tc = LLMTestCase(
                input=rendered_input,
                # 整列为空时填占位符：deepeval 会把空 actual_output 判缺参跳过，
                # 业务上"未输出"本身也要送评（与指标级空子字段占位符同口径）
                actual_output=out_raw if out_raw else "（空：模型该任务未输出任何内容）",
                expected_output=(row.get(col_exp) if col_exp else None) or None,
                name=name,
                metadata=(
                    {
                        k: row[v].strip()
                        for k, v in (("case_id", col_case), ("trigger_time", col_time))
                        if v and row.get(v)
                    }
                    or None
                ),
            )
            # 原始 JSON 参数集挂在私有属性：MetricView 按指标取素材/输出子字段
            tc._eval_params = params
            tc._eval_output = output_params
            # 输出列的原始内容（未剥离栅栏）：raw_input 类指标（如 json_format）
            # 按约定送评原始数据，不加工
            tc._eval_output_raw = (row.get(col_out, "") or "")
            test_cases.append(tc)
        if n_bad:
            print(f"⚠ {n_bad} 行 input_text/ai_response_content 非合法 JSON，已跳过")
        return test_cases

    # 标准格式
    test_cases = []
    for i, row in enumerate(rows, 1):
        if not (row.get("input", "") or "").strip():
            continue
        tags = [t.strip() for t in (row.get("tags") or "").split(";") if t.strip()]
        test_cases.append(
            LLMTestCase(
                input=row["input"],
                # 空输出填占位符：deepeval 会把空 actual_output 判缺参跳过
                actual_output=(row.get("actual_output") or "").strip() or "（空：模型该任务未输出任何内容）",
                expected_output=row.get("expected_output") or None,
                context=_split_list(row.get("context")),
                retrieval_context=_split_list(row.get("retrieval_context")),
                name=row.get("name") or f"{os.path.basename(path)}#L{i}",
                tags=tags or None,
            )
        )
    return test_cases


def _split_list(value):
    if not value:
        return None
    items = [v.strip() for v in str(value).split(";") if v.strip()]
    return items or None


def run_task(task: str, limit: int = None, resume: bool = False, offset: int = None):
    conf = TASKS[task]
    category = task.split("/")[0]
    cat_conf = CATEGORIES[category]
    spec = load_category_spec(cat_conf["config"], conf["criteria"])

    # 用例数：CLI --limit > 任务注册表 limit（留空/不配 = 全部）
    task_limit = limit if limit is not None else conf.get("limit")

    print(f"\n{'=' * 64}\n▶ 任务: {task} —— {conf['desc']}\n{'=' * 64}")

    # 参数化 input 模板（任务 YAML meta.input_template，{参数名} 引用 JSON 字段）
    input_template = (spec.get("meta") or {}).get("input_template")

    test_cases = load_test_cases_from_csv(conf["data"], conf.get("columns"), task_limit, input_template, offset)
    if not test_cases:
        print(f"⚠ {conf['data']} 无有效数据行，跳过")
        return None
    print(f"  数据: {len(test_cases)} 条用例 ← {conf['data']}"
          + (f"（第 {offset + 1} 行起" if offset else "")
          + (f"，采样前 {task_limit} 条）" if task_limit else ("）" if offset else "")))

    # 素材落档：把任务 YAML 各指标 retrieval_fields 的并集挂到原始用例的
    # retrieval_context 上，随 test_run JSON / Confident AI / 报告留痕
    # （judge 评分用的仍是 MetricView 按指标铸的定制视图，两者独立）
    attach_material_fields(test_cases, spec)

    # 断点续跑：从上次同任务结果中剔除已完整成功的用例
    if resume:
        done = _load_completed_case_names(task)
        before = len(test_cases)
        test_cases = [tc for tc in test_cases if tc.name not in done]
        print(f"  续跑: 跳过上次已成功用例 {before - len(test_cases)} 条，剩余 {len(test_cases)} 条")
        if not test_cases:
            print("  全部用例已成功，无需续跑")
            return None

    # 统一编号：同一次运行的 test_run JSON / MD 报告 / prompts 文档共用一个
    # run_id（任务-版本_日期_序号）。序号按 results 目录内已有编号取最大+1，
    # 保证当日递增且四类文件相互对应。
    version = str((spec.get("meta") or {}).get("hyperparameters", {}).get("template_version") or "")
    run_id = _next_run_id(task.replace("/", "-"), version)
    # fork 的 local_store 读取该环境变量固定 test_run JSON 文件名
    os.environ["DEEPEVAL_TEST_RUN_FILENAME"] = run_id

    metrics = build_metrics(cat_conf["config"], conf["criteria"], task, model=JUDGE_MODEL)
    # DeepEvalBaseLLM 把模型名存在 .name（豆包为接入点 ID，如 ep-xxx）
    judge_name = getattr(JUDGE_MODEL, "name", None) if JUDGE_MODEL else None
    print(f"  指标: {[getattr(m, 'name', m.__class__.__name__) for m in metrics]}")
    print(f"    （大类 {category} 通用 + 任务专属，同名任务优先）")
    print(f"  judge 模型: {judge_name} ({PROVIDER})\n")

    # 提示词说明文档（每次运行生成，与报告同目录；文件名用统一 run_id）
    prompt_doc = dump_prompt_doc(task, spec, RESULTS_DIR, run_id)
    if prompt_doc:
        print(f"✅ 提示词文档: {prompt_doc}")

    # evaluate 参数来自大类/任务 YAML 的 meta.evaluate（有默认值兜底）
    ev = spec.get("meta", {}).get("evaluate", {})
    disp = ev.get("display", {})
    err = ev.get("error", {})
    asy = ev.get("async", {})
    prefix = ev.get("identifier_prefix", task.replace("/", "-"))
    file_type = ev.get("report", {}).get("file_type", None)
    # 每个指标在报告展示的参数（该指标实际送评的视图）；None = 默认三参数全展示
    vp_cfg = ev.get("report", {}).get("view_params", None)

    from deepeval.test_run.test_run import TestRunResultDisplay

    _DISPLAY_OPTIONS = {
        "all": TestRunResultDisplay.ALL,
        "failing": TestRunResultDisplay.FAILING,
        "passing": TestRunResultDisplay.PASSING,
    }
    display_option = _DISPLAY_OPTIONS.get(
        str(disp.get("display_option", "all")).lower(), TestRunResultDisplay.ALL
    )

    # 超参数记录（版本化）：YAML meta.hyperparameters + 实际调用的模型
    # 评估标准（criteria/schema/阈值）迭代时在任务 YAML 改 template_version
    hyper_params = dict(spec.get("meta", {}).get("hyperparameters") or {})
    if judge_name:
        # model = 本次评估实际调用的 judge 模型（端点 ID + 提供方）
        hyper_params.setdefault("model", f"{judge_name} ({PROVIDER})")

    # 业务 prompt（被测系统给业务模型的提示词）：
    # 文本维护在 examples/finance_eval/prompts/<任务>/<版本名>.md（纯 prompt，文件名即版本名，
    # 与 categories 的任务目录同名；取目录内文件名最新的一版生效）。
    # - 本地（默认）：正文以纯文本随 hyperparameters 记录进 test_run JSON
    # - 云端（环境 PROMPT_PUSH_TO_CLOUD=true 时）：包成 Prompt 对象，evaluate
    #   自动按 alias push 到 Confident AI（云端按 alias 归集版本，可对比各版本得分）。
    #   注意：prompt 上云需要 Confident AI 试用/付费计划，未开通会报
    #   "An active trial or paid plan is required"，届时删掉该环境变量即可。
    prompt_text, prompt_version = _load_task_prompt(task)
    if prompt_text:
        alias = task.split("/", 1)[1] + "_prompt"
        hyper_params["prompt_version"] = prompt_version
        if os.getenv("PROMPT_PUSH_TO_CLOUD", "").lower() in ("1", "true", "yes"):
            from deepeval.prompt import Prompt

            hyper_params[alias] = Prompt(
                alias=alias, text_template=prompt_text
            )
        else:
            hyper_params[f"{alias}_text"] = prompt_text

    result = evaluate(
        test_cases=test_cases,
        metrics=metrics,
        identifier=f"{prefix}-{task.split('/')[1]}",
        hyperparameters=hyper_params or None,
        async_config=AsyncConfig(
            run_async=asy.get("run_async", True),
            throttle_value=asy.get("throttle_value", 0),
            max_concurrent=asy.get("max_concurrent", 20),
        ),
        display_config=DisplayConfig(
            show_indicator=True,
            print_results=disp.get("print_results", True),
            display_option=display_option,
            truncate_passing_cases=disp.get("truncate_passing_cases", True),
            results_folder=RESULTS_DIR,
            file_type=file_type,
            file_output_dir=RESULTS_DIR if file_type else None,
            inspect_after_run=False,
        ),
        error_config=ErrorConfig(
            ignore_errors=err.get("ignore_errors", True),
            skip_on_missing_params=err.get("skip_on_missing_params", True),
        ),
    )

    # 超时熔断提示：报告已完成部分行数 + 原始 CSV 总行数
    from deepeval.utils import get_timeout_case_count

    if get_timeout_case_count() > 0:
        total_rows = _csv_row_count(conf["data"], conf.get("columns"))
        n_done = len(result.test_results) if result else 0
        # 最后执行用例的绝对行号（用例名 case<N> 提取；含 offset 起点前的空档）
        next_offset = n_done + (offset or 0)
        for tr in reversed(result.test_results or []):
            m = re.search(r"case(\d+)", tr.name or "")
            if m:
                next_offset = int(m.group(1))
                break
        print(
            f"\n⚠ 触发超时熔断：本次实际跑完 {n_done} 行（其中 {get_timeout_case_count()} 行超时判 ERROR）"
            f" / 原始 CSV（按任务筛选后）共 {total_rows} 行。"
            f"已完成部分已保存并推送；超时行可用 --resume 重跑，或 --offset {next_offset} 跳到后续行。"
        )

    # Markdown 报告（标题/文件名与 test_run JSON 等统一 run_id）
    latest = _latest_test_run()
    if latest:
        from importlib.util import module_from_spec, spec_from_file_location

        s = spec_from_file_location(
            "report_md",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "report_md.py"),
        )
        mod = module_from_spec(s)
        s.loader.exec_module(mod)
        md_path = mod.generate(
            latest,
            task.replace("/", "-"),
            out_dir=RESULTS_DIR,
            include_reason=ev.get("report", {}).get("include_reason", True),
            run_id=run_id,
            view_params=vp_cfg,
        )
        print(f"✅ Markdown 报告: {md_path}")

    # HTML 报告（文件名 report_test_run_<run_id>.html，与 JSON 统一编号）
    if latest:
        from importlib.util import module_from_spec, spec_from_file_location

        s = spec_from_file_location(
            "report_html",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "report_html.py"),
        )
        mod = module_from_spec(s)
        s.loader.exec_module(mod)
        html_path = mod.generate(
            latest,
            out_path=os.path.join(RESULTS_DIR, f"report_test_run_{run_id}.html"),
            view_params=vp_cfg,
        )
        print(f"✅ HTML 报告: {html_path}")

    return result


def _latest_test_run():
    runs = sorted(glob.glob(os.path.join(RESULTS_DIR, "test_run_*.json")))
    return runs[-1] if runs else None


def _csv_row_count(path: str, columns: dict = None) -> int:
    """原始 CSV 的数据行数（与 load_test_cases_from_csv 同口径：按 ai_task 筛选后）。"""
    rows = _read_csv_rows(path)
    task_filter = (columns or {}).get("ai_task")
    if task_filter:
        rows = [r for r in rows if (r.get("ai_task") or "").strip() == task_filter]
    return len(rows)


def _next_run_id(task_file: str, version: str) -> str:
    import re as _re
    import time as _time

    date_str = _time.strftime("%Y%m%d")
    v_part = f"{version}_" if version else ""
    stem = f"{task_file}_{v_part}{date_str}_"
    pat = _re.compile(rf"{_re.escape(stem)}(\d+)")
    seq = 1
    if os.path.isdir(RESULTS_DIR):
        for fn in os.listdir(RESULTS_DIR):
            m = pat.search(fn)
            if m:
                seq = max(seq, int(m.group(1)) + 1)
    return f"{stem}{seq:03d}"


def _load_task_prompt(task: str):
    """读取任务的业务 prompt：examples/finance_eval/prompts/<任务>/<版本名>.md。

    - 目录名 = 任务名（如 prompts/case_summary/），文件名（去 .md）= 版本名
    - 文件内容为纯 prompt（无 frontmatter、无解释文字）
    - 取文件名排序最大（最新版本）的一版；目录不存在返回 (None, None)
    """
    task_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "prompts",
        task.split("/", 1)[1],
    )
    if not os.path.isdir(task_dir):
        return None, None
    mds = sorted(
        f for f in os.listdir(task_dir)
        if f.lower().endswith(".md")
    )
    if not mds:
        return None, None
    latest = mds[-1]
    with open(os.path.join(task_dir, latest), "r", encoding="utf-8") as f:
        text = f.read().strip()
    return (text, None) if not text else (text, latest[:-3])


def _load_completed_case_names(task: str) -> set:
    """读取最新一次 test_run JSON，返回该任务中所有指标均执行成功（无 ERROR）的用例名。

    用例名含 case_id/trigger_time（load_test_cases_from_csv 生成），可作为跨次运行的稳定键。
    """
    latest = _latest_test_run()
    if not latest:
        return set()
    try:
        with open(latest, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return set()
    done = set()
    for tc in data.get("testCases", []):
        md = tc.get("metricsData") or []
        # 有指标数据且没有任何 error 字段 → 该用例完整跑完
        if md and not any(m.get("error") for m in md):
            done.add(tc.get("name") or "")
    return done


# ---------- 提示词说明文档 ----------

# 各指标类型的 LLM 调用序列：模板文件名（相对 deepeval/metrics/<目录>/templates/）
# 仅用于 dump_prompt_doc 原样输出提示词；未列出的类型无 LLM 评分调用
_METRIC_TEMPLATES = {
    "geval": ("g_eval", ["generate_evaluation_steps", "generate_evaluation_results"]),
    "summarization": ("summarization", [
        "generate_questions", "generate_answers", "generate_alignment_verdicts",
    ]),
    "faithfulness": ("faithfulness", [
        "generate_truths", "generate_claims", "generate_verdicts",
    ]),
    "answer_relevancy": ("answer_relevancy", [
        "generate_statements", "generate_verdicts",
    ]),
}

_TEMPLATES_ROOT = os.path.join(_REPO_ROOT, "deepeval", "metrics")


def _raw_template(metric_dir: str, name: str) -> str:
    path = os.path.join(_TEMPLATES_ROOT, metric_dir, "templates", f"{name}.txt")
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def dump_prompt_doc(task: str, spec: dict, out_dir: str, run_id: str = None) -> str:
    """生成本次任务的提示词文档：只含给模型的 user 原文（system 一律为无）。

    模板原样输出；{{ criteria }} 替换为 YAML 中的 criteria 原文，
    其余用例字段占位符保持 Jinja2 原样（input / actual_output 等即代指用户输入/模型输出）。
    run_id 传入时文件名与其余产物统一编号（prompts-<run_id>.md）。
    """
    import time as _time

    task_file = task.replace("/", "-")
    if run_id:
        report_id = f"prompts-{run_id}"
    else:
        from report_md import _next_seq

        date_str = _time.strftime("%Y%m%d")
        seq = _next_seq(out_dir, f"prompts-{task_file}", date_str)
        report_id = f"prompts-{task_file}_{date_str}_{seq:03d}"
    out_path = os.path.join(out_dir, f"{report_id}.md")

    lines = [
        f"# {report_id}",
        "",
        f"> 任务：**{task}** · 生成时间 {_time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "以下为发给 judge 模型的提示词。所有请求 system 一律为无，"
        "user 即下方各模板原文；`{{ input }}` 为用户输入，`{{ actual_output }}` 为模型输出。",
        "",
    ]

    n = 0
    for key, cfg in spec.get("metrics", {}).items():
        kind = cfg.get("metric", "geval")
        entry = _METRIC_TEMPLATES.get(kind)
        if not entry:
            continue  # json_correctness / pattern_match 等本地判定，无提示词
        metric_dir, templates = entry
        n += 1
        lines.append(f"## {n}. {cfg.get('name', key)}")
        lines.append("")
        for tpl in templates:
            content = _raw_template(metric_dir, tpl)
            if kind == "geval" and tpl == "generate_evaluation_steps":
                content = content.replace("{{ criteria }}", cfg.get("criteria", "{{ criteria }}"))
            lines.append(f"### user（{tpl}）")
            lines.append("")
            lines.append("```")
            lines.append(content)
            lines.append("```")
            lines.append("")

    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return out_path


def make_pretty_report():
    runs = sorted(glob.glob(os.path.join(RESULTS_DIR, "test_run_*.json")))
    if not runs:
        return
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location(
        "report_html",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "report_html.py"),
    )
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)

    out = mod.generate(runs[-1])
    print(f"\n✅ 美化报告: {out}")


def main():
    parser = argparse.ArgumentParser(description="按大类/任务运行 DeepEval 评估")
    parser.add_argument(
        "--category",
        help=f"运行整个大类。可选：{', '.join(CATEGORIES.keys())}",
    )
    parser.add_argument(
        "--task",
        help="运行指定任务，逗号分隔，如 extraction/case_summary",
    )
    parser.add_argument("--list", action="store_true", help="列出大类与任务后退出")
    parser.add_argument(
        "--limit", type=int,
        help="每任务最多评估的用例数（采样），覆盖任务注册表 limit；不传则用任务默认（未配置=全部）",
    )
    parser.add_argument(
        "--offset", type=int,
        help="跳过 CSV 前 N 行再取用例（与 --limit 配合分批跑：先 --limit 100，再 --offset 100 --limit 100，再 --offset 200 …）",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="断点续跑：读取最近一次结果，跳过全部指标已成功（无ERROR）的用例",
    )
    args = parser.parse_args()

    if args.list:
        print("可用大类：")
        for name, conf in CATEGORIES.items():
            print(f"  {name:12s} {conf['desc']}")
            print(f"  {'':12s} 配置: {conf['config']}")
            print(f"  {'':12s} 任务:")
            for t in tasks_in_category(name):
                print(f"  {'':14s}- {t}  （{TASKS[t]['desc']}）")
            print()
        return

    # 默认：全部任务
    selected = list(TASKS.keys())
    if args.category:
        if args.category not in CATEGORIES:
            parser.error(f"未知大类: {args.category}。可选：{', '.join(CATEGORIES.keys())}")
        selected = tasks_in_category(args.category)
    if args.task:
        wanted = [t.strip() for t in args.task.split(",") if t.strip()]
        unknown = [t for t in wanted if t not in TASKS]
        if unknown:
            parser.error(f"未知任务: {unknown}。可选：{', '.join(TASKS.keys())}")
        selected = wanted

    failed_tasks = []
    for task in selected:
        result = run_task(task, limit=args.limit, resume=args.resume, offset=args.offset)
        if result is None:
            continue
        # 任一用例任一指标 success=False → 记为未达标
        for tr in result.test_results:
            if any(md.success is False for md in tr.metrics_data):
                failed_tasks.append(task)
                break
    if failed_tasks:
        print(f"\n存在未达标任务: {failed_tasks}")
        sys.exit(1)


if __name__ == "__main__":
    main()
