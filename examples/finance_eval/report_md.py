"""Markdown 评估报告生成器（纯标准库）。

用法：
    python examples/finance_eval/report_md.py <test_run.json> <任务名>
    # 或不带参数由 run_eval.py 调用

报告标题（也是文件名）：任务名_版本_日期_编号（当日第 N 次，按已有文件计数递增）
默认包含每个指标的 reason。model / template_version 取自 test_run 的 hyperParameters。
"""

import glob
import json
import os
import re
import time


def _next_seq(results_dir: str, task: str, date_str: str, version: str = "") -> int:
    """按已有报告文件名计算当日下一个编号（版本段缺省时兼容旧命名）。"""
    seq = 1
    v_part = f"{version}_" if version else ""
    pattern = re.compile(
        rf"{re.escape(task)}_{re.escape(v_part)}{re.escape(date_str)}_(\d+)\.md$"
    )
    if os.path.isdir(results_dir):
        for fn in os.listdir(results_dir):
            m = pattern.match(fn)
            if m:
                seq = max(seq, int(m.group(1)) + 1)
    return seq


def _md_escape(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\r\n", "\n")


def _details_block(title: str, content: str) -> str:
    content = (content or "").strip()
    if not content:
        return ""
    if "```" in content:
        return f"<details><summary>{title}</summary>\n\n{content}\n\n</details>\n"
    return (
        f"<details><summary>{title}</summary>\n\n```\n{content}\n```\n\n</details>\n"
    )


# 指标参数视图默认展示的参数（任务 YAML meta.report.view_params 可覆盖）
_DEFAULT_VIEW_PARAMS = ["input", "actualOutput", "retrievalContext"]

_VP_LABELS = {
    "input": "Input",
    "actualOutput": "Actual Output",
    "retrievalContext": "Retrieval Context（素材）",
}

# YAML 配置允许 snake_case 写法（actual_output / retrieval_context），统一归一
_VP_ALIASES = {
    "input": "input",
    "actual_output": "actualOutput",
    "actualOutput": "actualOutput",
    "retrieval_context": "retrievalContext",
    "retrievalContext": "retrievalContext",
}


def _normalize_view_params(view_params: list) -> list:
    """配置的参数名归一为 viewParams 的 camelCase 键（未知名剔除）。"""
    return [
        _VP_ALIASES.get(p, p)
        for p in (view_params or [])
        if _VP_ALIASES.get(p, p) in _VP_LABELS
    ]


def generate(json_path: str, task: str, out_dir: str = None, include_reason: bool = True, run_id: str = None, view_params: list = None) -> str:
    """从 test_run JSON 生成 Markdown 报告，返回文件路径。

    run_id 传入时文件名直接用该统一编号（与 test_run JSON / prompts 文档一致），
    否则按目录内已有文件自行计算 任务_版本_日期_序号。

    view_params: 每个指标要展示的参数名列表，可选项 input/actualOutput/retrievalContext。
    None（默认）= 三者全展示；空列表 = 全部关闭；子集 = 只展示配置的参数。
    无内容的参数不渲染；与用例级 Input/Actual Output 折叠块相互独立。
    """
    if view_params is None:
        view_params = _DEFAULT_VIEW_PARAMS
    else:
        view_params = _normalize_view_params(view_params)
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = data.get("testCases", [])
    out_dir = out_dir or (os.path.dirname(json_path) or ".")

    # judge 模型名（取各指标 evaluationModel 的并集）
    judge_models = []
    for m in (x for tc in cases for x in (tc.get("metricsData") or [])):
        em = m.get("evaluationModel")
        if em and em not in judge_models:
            judge_models.append(em)
    judge_str = " / ".join(judge_models) or "—"

    # 超参数（版本信息）：hyperparameters 里的 model / template_version
    hyper = data.get("hyperparameters") or {}
    model_str = hyper.get("model") or judge_str
    version = str(hyper.get("template_version") or "")

    if run_id:
        report_id = run_id
    else:
        date_str = time.strftime("%Y%m%d")
        seq = _next_seq(out_dir, task, date_str, version)
        report_id = f"{task}_{f'{version}_' if version else ''}{date_str}_{seq:03d}"
    out_path = os.path.join(out_dir, f"{report_id}.md")

    all_metrics = [m for tc in cases for m in (tc.get("metricsData") or [])]
    n_pass = sum(1 for m in all_metrics if m.get("success"))
    n_fail = sum(1 for m in all_metrics if m.get("success") is False)
    pass_rate = n_pass / len(all_metrics) * 100 if all_metrics else 0
    scored = [m["score"] for m in all_metrics if isinstance(m.get("score"), (int, float))]
    avg = sum(scored) / len(scored) if scored else 0

    lines = [
        f"# {report_id}",
        "",
        f"> 任务：**{task}** · 生成时间 {time.strftime('%Y-%m-%d %H:%M:%S')}"
        f" · model：**{model_str}**"
        + (f" · template_version：**{version}**" if version else "")
        + f" · 用例 {len(cases)} · 指标 {len(all_metrics)}",
        "",
        "## 总览",
        "",
        f"- 指标通过率：**{pass_rate:.0f}%**（{n_pass} 通过 / {n_fail} 失败）",
        f"- 平均得分：**{avg:.2f}**",
        "",
        "## 指标汇总",
        "",
        "| 指标 | 平均分 | 通过/失败 | 通过率 |",
        "|---|---:|---:|---:|",
    ]

    agg = {}
    order = []
    for m in all_metrics:
        name = m.get("name") or "metric"
        if name not in agg:
            agg[name] = {"scores": [], "pass": 0, "fail": 0}
            order.append(name)
        e = agg[name]
        if isinstance(m.get("score"), (int, float)):
            e["scores"].append(m["score"])
        if m.get("success"):
            e["pass"] += 1
        elif m.get("success") is False:
            e["fail"] += 1
    for name in order:
        e = agg[name]
        a = sum(e["scores"]) / len(e["scores"]) if e["scores"] else 0
        total = e["pass"] + e["fail"]
        rate = e["pass"] / total * 100 if total else 0
        lines.append(f"| {_md_escape(name)} | {a:.2f} | {e['pass']}/{e['fail']} | {rate:.0f}% |")

    lines += ["", "## 用例明细", ""]
    for idx, tc in enumerate(cases, 1):
        md = tc.get("metricsData") or []
        tc_pass = sum(1 for m in md if m.get("success"))
        tc_fail = sum(1 for m in md if m.get("success") is False)
        status = "✅ PASS" if tc.get("success") else "❌ FAIL"
        lines += [
            f"### {idx}. {tc.get('name') or ''} {status}",
            "",
            f"通过 {tc_pass} / 失败 {tc_fail} · 耗时 {float(tc.get('runDuration')):.2f}s" if tc.get("runDuration") is not None else f"通过 {tc_pass} / 失败 {tc_fail}",
            "",
            "| 指标 | 得分 | 阈值 | 结果 |",
            "|---|---:|---:|---|",
        ]
        for m in md:
            s = m.get("score")
            s_str = f"{s:.2f}" if isinstance(s, (int, float)) else "—"
            ok = m.get("success")
            mark = "✅" if ok else "❌" if ok is False else "⏭️"
            th = m.get("threshold")
            th_str = f"{th:.2f}" if isinstance(th, (int, float)) else "—"
            lines.append(
                f"| {_md_escape(m.get('name') or '')} | {s_str} "
                f"| {th_str} | {mark} |"
            )
        lines.append("")
        if include_reason:
            lines.append("#### 评分理由")
            for m in md:
                reason = (m.get("reason") or "").strip()
                if reason:
                    lines.append(
                        f"- **{m.get('name') or ''}**：{_md_escape(reason)}"
                    )
            lines.append("")
        # 指标参数来源：按 input / actualOutput / retrievalContext 拆分为
        # 独立折叠块（默认收起），该参数无内容则不展示；
        # 完整内容见用例级 Input / Actual Output / Retrieval Context 折叠块
        if view_params:
            for m in md:
                vp = m.get("viewParams") or {}
                mname = m.get("name") or ""
                for key in view_params:
                    v = vp.get(key)
                    if v:
                        lines.append(
                            _details_block(
                                f"{_VP_LABELS.get(key, key)} · {mname}",
                                str(v),
                            )
                        )
        lines.append(_details_block("Input", tc.get("input")))
        lines.append(_details_block("Actual Output", tc.get("actualOutput")))
        lines.append("")

    content = "\n".join(lines)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    return out_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 2:
        src, task = sys.argv[1], sys.argv[2]
    else:
        runs = sorted(glob.glob(".deepeval_results/test_run_*.json"))
        if not runs:
            sys.exit("未找到 test_run JSON")
        src = runs[-1]
        task = "eval"
    print(generate(src, task))
