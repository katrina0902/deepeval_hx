"""美化版 HTML 评估报告生成器（纯标准库，无第三方依赖）。

用法：
    python examples/finance_eval/report_html.py .deepeval_results/test_run_xxx.json
    # 或不带参数，自动选 .deepeval_results 下最新的 test_run_*.json

从 DeepEval 导出的 test_run JSON 生成一个可交互的单文件 HTML 报告：
- 总览卡片（通过率/平均分/指标数/用例数）
- 指标汇总表（平均分、通过率、进度条）
- 每个用例的明细：指标评分条、通过状态、评分理由（可折叠展开 verbose 日志）
"""

import glob
import html
import json
import os
import sys
import time

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

_THEME_CSS = """
:root {
  --bg: #ffffff; --panel: #ffffff; --panel2: #f5f6f8;
  --border: #dde1e7; --text: #1a1d23; --muted: #6b7280;
  --green: #15803d; --red: #dc2626; --amber: #b45309;
  --purple: #7c3aed; --blue: #2563eb; --cyan: #0e7490;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg); color: var(--text);
  font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
  padding: 32px 20px 80px; line-height: 1.6;
}
.wrap { max-width: 1080px; margin: 0 auto; }
h1 { font-size: 22px; margin-bottom: 4px; }
h1 .logo { color: var(--purple); }
.sub { color: var(--muted); font-size: 13px; margin-bottom: 28px; }
h2 { font-size: 16px; margin: 36px 0 14px; color: var(--text);
     border-left: 3px solid var(--purple); padding-left: 10px; }

.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; }
.card { background: var(--panel); border: 1px solid var(--border);
        border-radius: 12px; padding: 18px 20px; }
.card .label { color: var(--muted); font-size: 12px; margin-bottom: 6px; }
.card .value { font-size: 26px; font-weight: 700; }
.card .value.good { color: var(--green); } .card .value.bad { color: var(--red); }

table { width: 100%; border-collapse: collapse; background: var(--panel);
        border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
th { text-align: left; font-size: 12px; color: var(--muted); font-weight: 600;
     padding: 10px 14px; background: var(--panel2); border-bottom: 1px solid var(--border); }
td { padding: 10px 14px; font-size: 13.5px; border-bottom: 1px solid var(--border); vertical-align: top; }
tr:last-child td { border-bottom: none; }

.badge { display: inline-block; padding: 2px 10px; border-radius: 999px;
         font-size: 12px; font-weight: 700; }
.badge.pass { background: rgba(21,128,61,.12); color: var(--green); }
.badge.fail { background: rgba(220,38,38,.10); color: var(--red); }
.badge.skip { background: rgba(180,83,9,.12); color: var(--amber); }

.score-wrap { display: flex; align-items: center; gap: 10px; min-width: 150px; }
.bar { flex: 1; height: 7px; background: var(--panel2); border-radius: 4px; overflow: hidden; }
.bar > i { display: block; height: 100%; border-radius: 4px; }
.score-num { font-variant-numeric: tabular-nums; font-weight: 700; width: 38px; text-align: right; }

.case { background: var(--panel); border: 1px solid var(--border);
        border-radius: 12px; margin-bottom: 18px; overflow: hidden; }
.case-head { display: flex; align-items: center; gap: 12px; padding: 14px 18px;
             background: var(--panel2); flex-wrap: wrap; }
.case-head .name { font-weight: 700; font-size: 14.5px; }
.case-head .meta { color: var(--muted); font-size: 12px; margin-left: auto; }
.io { padding: 14px 18px; display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 800px) { .io { grid-template-columns: 1fr; } }
.io details { background: var(--panel2); border: 1px solid var(--border);
              border-radius: 8px; padding: 10px 14px; }
.io summary { cursor: pointer; font-size: 13px; color: var(--cyan); font-weight: 600; }
.io pre { margin-top: 10px; font-size: 12px; color: var(--text);
         white-space: pre-wrap; word-break: break-all;
         max-height: 320px; overflow: auto; font-family: Consolas, monospace; }

.metric-row { padding: 14px 18px; border-top: 1px solid var(--border); }
.metric-top { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.metric-name { font-weight: 700; font-size: 14px; }
.reason { color: var(--text); font-size: 13px; margin-top: 8px;
          white-space: pre-wrap; }
details.verbose summary { cursor: pointer; font-size: 12px; color: var(--blue);
                          margin-top: 8px; user-select: none; }
details.verbose pre { margin-top: 8px; background: var(--panel2);
                      border: 1px solid var(--border); border-radius: 8px;
                      padding: 12px; font-size: 12px; color: var(--text);
                      white-space: pre-wrap; max-height: 400px; overflow: auto;
                      font-family: Consolas, monospace; }
details.view-params { margin-top: 10px; }
details.view-params summary { cursor: pointer; font-size: 12px; color: var(--purple);
                              user-select: none; }
details.view-params pre { margin-top: 8px; background: var(--panel2);
                          border: 1px solid var(--border); border-radius: 8px;
                          padding: 12px; font-size: 12px; color: var(--text);
                          white-space: pre-wrap; max-height: 400px; overflow: auto;
                          font-family: Consolas, monospace; }
footer { margin-top: 40px; color: var(--muted); font-size: 12px; text-align: center; }
"""


def _score_color(score, success):
    if success is None:
        return "var(--amber)"
    return "var(--green)" if success else "var(--red)"


def _fmt(v, default="—"):
    return default if v is None else v


def _pretty_json(text: str) -> str:
    """内容是 JSON 对象/数组串时格式化（每字段换行、缩进），否则原样返回。"""
    t = (text or "").strip()
    if not t or t[0] not in "{[":
        return text or ""
    try:
        return json.dumps(json.loads(t), ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, ValueError):
        return text or ""


def _view_params_html(metric: dict, view_params: list) -> str:
    """该指标实际取了哪些值：按参数拆分为独立折叠块（默认收起；无内容不渲染）。"""
    vp = metric.get("viewParams") or {}
    blocks = []
    for key in view_params:
        v = vp.get(key)
        if v:
            blocks.append(
                f'<details class="view-params"><summary>{html.escape(_VP_LABELS.get(key, key))}</summary>'
                f"<pre>{html.escape(str(v))}</pre></details>"
            )
    return "".join(blocks)


def _case_html(tc, view_params=None):
    metrics = tc.get("metricsData") or []
    pass_n = sum(1 for m in metrics if m.get("success"))
    fail_n = sum(1 for m in metrics if m.get("success") is False)
    status_badge = (
        '<span class="badge pass">PASS</span>' if tc.get("success")
        else '<span class="badge fail">FAIL</span>'
    )
    rows = []
    for m in metrics:
        score = m.get("score")
        success = m.get("success")
        color = _score_color(score, success)
        pct = f"{score * 100:.0f}%" if isinstance(score, (int, float)) else "0%"
        badge = (
            '<span class="badge pass">PASS</span>' if success
            else '<span class="badge fail">FAIL</span>' if success is False
            else '<span class="badge skip">SKIP</span>'
        )
        verbose = ""
        if m.get("verboseLogs"):
            verbose = (
                f'<details class="verbose"><summary>Verbose Logs（评估步骤 / 中间结果）</summary>'
                f"<pre>{html.escape(str(m['verboseLogs']))}</pre></details>"
            )
        vp_html = _view_params_html(m, view_params) if view_params else ""
        rows.append(
            f"""<div class="metric-row">
  <div class="metric-top">
    {badge}
    <span class="metric-name">{html.escape(m.get('name') or 'metric')}</span>
    <span class="score-wrap" style="min-width:160px">
      <span class="bar"><i style="width:{pct};background:{color}"></i></span>
      <span class="score-num" style="color:{color}">{f'{score:.2f}' if isinstance(score, (int, float)) else '—'}</span>
    </span>
    <span style="color:var(--muted);font-size:12px">阈值 {_fmt(m.get('threshold'))}</span>
    <span style="color:var(--muted);font-size:12px">模型 {html.escape(_fmt(m.get('evaluationModel'), ''))}</span>
  </div>
  <div class="reason">{html.escape(m.get('reason') or '')}</div>
  {verbose}
  {vp_html}
</div>"""
        )
    rc = tc.get("retrievalContext") or []
    rc_html = ""
    if rc:
        rc_html = (
            f'<details><summary>Retrieval Context（素材 · {len(rc)} 块）</summary>'
            f"<pre>{html.escape(chr(10).join(_pretty_json(str(x)) for x in rc))}</pre></details>"
        )
    return f"""<div class="case">
  <div class="case-head">
    {status_badge}
    <span class="name">{html.escape(tc.get('name') or 'test_case')}</span>
    <span class="meta">{pass_n} 通过 / {fail_n} 失败 · {f"{float(tc.get('runDuration')):.2f}s" if tc.get("runDuration") is not None else ''}</span>
  </div>
  <div class="io">
    <details><summary>Input（{len(tc.get('input') or '')} 字符）</summary>
      <pre>{html.escape(_pretty_json(tc.get('input') or ''))}</pre></details>
    <details><summary>Actual Output（{len(tc.get('actualOutput') or '')} 字符）</summary>
      <pre>{html.escape(_pretty_json(tc.get('actualOutput') or ''))}</pre></details>
    {rc_html}
  </div>
  {''.join(rows)}
</div>"""


def generate(json_path: str, out_path: str = None, view_params: list = None) -> str:
    """view_params: 每个指标展示的参数名列表（input/actualOutput/retrievalContext）。
    None = 默认三参数全展示；空列表 = 关闭；子集 = 只展示配置的参数。"""
    if view_params is None:
        view_params = _DEFAULT_VIEW_PARAMS
    else:
        view_params = _normalize_view_params(view_params)
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = data.get("testCases", [])
    conv = data.get("conversationalTestCases") or []
    for c in conv:
        turns = c.get("turns") or []
        cases.append({
            "name": c.get("scenario") or c.get("name") or "conversational",
            "input": "\n".join(f"[{t.get('role')}] {t.get('content')}" for t in turns),
            "actualOutput": turns[-1].get("content") if turns else "",
            "metricsData": c.get("metricsData") or [],
            "success": c.get("success"),
            "runDuration": c.get("runDuration"),
        })

    all_metrics = [m for tc in cases for m in (tc.get("metricsData") or [])]
    n_case = len(cases)
    n_metric = len(all_metrics)
    n_pass = sum(1 for m in all_metrics if m.get("success"))
    n_fail = sum(1 for m in all_metrics if m.get("success") is False)
    pass_rate = (n_pass / n_metric * 100) if n_metric else 0
    scored = [m["score"] for m in all_metrics if isinstance(m.get("score"), (int, float))]
    avg_score = sum(scored) / len(scored) if scored else 0

    agg = {}
    for m in all_metrics:
        name = m.get("name") or "metric"
        e = agg.setdefault(name, {"scores": [], "pass": 0, "fail": 0})
        if isinstance(m.get("score"), (int, float)):
            e["scores"].append(m["score"])
        if m.get("success"):
            e["pass"] += 1
        elif m.get("success") is False:
            e["fail"] += 1
    agg_rows = []
    for name, e in sorted(agg.items()):
        avg = sum(e["scores"]) / len(e["scores"]) if e["scores"] else 0
        total = e["pass"] + e["fail"]
        rate = e["pass"] / total * 100 if total else 0
        color = "var(--green)" if rate >= 80 else "var(--amber)" if rate >= 50 else "var(--red)"
        agg_rows.append(
            f"""<tr><td>{html.escape(name)}</td>
<td><span class="score-wrap"><span class="bar"><i style="width:{avg*100:.0f}%;background:{color}"></i></span>
<span class="score-num" style="color:{color}">{avg:.2f}</span></span></td>
<td>{e['pass']} / {e['fail']}</td><td>{rate:.0f}%</td><td>{total}</td></tr>"""
        )

    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    doc = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>评估报告 · {html.escape(data.get('identifier') or json_path)}</title>
<style>{_THEME_CSS}</style></head><body><div class="wrap">
<h1><span class="logo">◆</span> DeepEval 评估报告{(' · ' + html.escape(data['identifier'])) if data.get('identifier') else ''}</h1>
<div class="sub">生成时间 {ts} · 数据源 {html.escape(os.path.basename(json_path))}</div>

<div class="cards">
  <div class="card"><div class="label">指标通过率</div>
    <div class="value {'good' if pass_rate>=80 else 'bad' if pass_rate<50 else ''}">{pass_rate:.0f}%</div></div>
  <div class="card"><div class="label">平均得分</div><div class="value">{avg_score:.2f}</div></div>
  <div class="card"><div class="label">通过 / 失败</div>
    <div class="value"><span style="color:var(--green)">{n_pass}</span>
    <span style="color:var(--muted);font-size:18px">/</span>
    <span style="color:var(--red)">{n_fail}</span></div></div>
  <div class="card"><div class="label">用例数 / 指标数</div>
    <div class="value">{n_case} <span style="color:var(--muted);font-size:18px">/</span> {n_metric}</div></div>
</div>

<h2>指标汇总</h2>
<table><thead><tr><th>指标</th><th>平均分</th><th>通过/失败</th><th>通过率</th><th>总数</th></tr></thead>
<tbody>{''.join(agg_rows)}</tbody></table>

<h2>用例明细</h2>
{''.join(_case_html(tc, view_params) for tc in cases) or '<p style="color:var(--muted)">无数据</p>'}

<footer>由 examples/finance_eval/report_html.py 生成 · DeepEval test_run JSON → 单文件 HTML</footer>
</div></body></html>"""

    if out_path is None:
        base = os.path.splitext(os.path.basename(json_path))[0]
        out_dir = os.path.dirname(json_path) or "."
        out_path = os.path.join(out_dir, f"report_{base}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
    return out_path


if __name__ == "__main__":
    if len(sys.argv) > 1:
        src = sys.argv[1]
    else:
        runs = sorted(glob.glob(".deepeval_results/test_run_*.json"))
        if not runs:
            sys.exit("未找到 test_run JSON，先运行评估，或指定路径")
        src = runs[-1]
    path = generate(src)
    print(f"✅ 美化报告已生成: {path}")
