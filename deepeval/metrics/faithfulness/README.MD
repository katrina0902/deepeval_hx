# 事实忠实度
## 定义
事实忠实度（Factfulness）是指模型输出是否基于检索上下文中的事实。
只看是否和检索上下文冲突，**不看回答是否贴合用户提问**; （模型输出是否基于检索上下文中的事实）

### 原理
Judge 把模型输出拆成多条独立事实陈述；逐条判断**这条陈述是否能被 retrieval_context 支撑**

### 公式
公式：`忠实度 = 可被上下文支撑的事实条数 / 总事实条数` → 映射 0~1

## 调用顺序:
素材 retrieval_context ──┐
actual_output ───────────┤
                         ▼
① generate_truths   从retrieval_context提取事实清单（受 truths_extraction_limit 限制条数）
                         │ truths
actual_output ───────────┤
                         ▼
② generate_claims   把模型输出拆成原子断言（claims）
                         │ claims + truths
                         ▼
③ generate_verdicts 逐条 claim 判定"素材能否找到依据"（yes/no + 原因）
                         │ verdicts
                   本地算分 score = yes数/总数   ← 无 LLM
                         │ score + verdicts
                         ▼
④ generate_reason   汇总判定结果写中文评分理由