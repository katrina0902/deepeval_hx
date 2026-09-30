# 回答相关性
## 定义
回答相关性（Answer Relevancy）是指模型输出是否与用户问题相关。
不检查事实真假，只管和用户问题是否相关。; （模型输出是否有利于回复用户问题）

### 原理
Judge 判断模型输出是否**针对用户输入作答**，有没有答非所问、跑题。

### 公式
score = verdicts 中 != "no" 的条数 / verdicts 总条数

## 调用顺序:
① generate_statements  → LLM 把输出拆成陈述列表
② generate_verdicts    → LLM 逐条判"相关/不相关"+各写一句原因(每条陈述分数及原因)
                        ↓ 本地：score = 相关数/总数
③ generate_reason→ 输入=②的原因+计算好的score+input
                        → LLM 只输出 {"reason": "..."}(整个输出分数及原因)