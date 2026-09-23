[LLMTestCase 全部参数(24 个)](deepeval/test_case/llm_test_case.py)

[evaluate全部可选参数](deepeval/evaluate/evaluate.py)

[DeepEval 全部50个指标](deepeval/metrics/__init__.py)

[基类参数base](deepeval/metrics/base_metric.py)

[GEval参数](deepeval/metrics/g_eval/g_eval.py)

[prompt模板](deepeval/metrics/<指标>/templates/)
需要转换为中文;更改prompt内容后，需要重编译：```python scripts/compile_metric_templates.py```

context	:提供给模型的事实依据（无论来源）
retrieval_context:RAG 检索器实际返回的文档块（顺序敏感）

模板：

import os
os.environ["DEEPEVAL_DEBUG"] = "1"

示例：
信息提取：SummarizationMetric(评估摘要的质量:忠实度、覆盖度)+FaithfulnessMetric+GEval+AnswerRelevancyMetric

纯摘要/结构化提取	AnswerRelevancy + GEval(事实忠实性) + GEval(完整性) + JsonCorrectness + Summarization
RAG 问答	AnswerRelevancy + Faithfulness + Hallucination + Contextual 三件套
Agent 工作流	TaskCompletion + ToolCorrectness + StepEfficiency + AgentLoopDetection（配 tracing）
客服机器人	ConversationCompleteness + RoleAdherence + KnowledgeRetention + TopicAdherence
合规审查	PIILeakage + NonAdvice + Misuse + RoleViolation
模型选型 A/B	ArenaGEval + compare()
