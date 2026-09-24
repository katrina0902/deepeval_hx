[LLMTestCase 全部参数(24 个)](deepeval/test_case/llm_test_case.py)

[evaluate全部可选参数](deepeval/evaluate/evaluate.py)

[DeepEval 全部50个指标](deepeval/metrics/__init__.py)

[基类参数base](deepeval/metrics/base_metric.py)

[GEval参数](deepeval/metrics/g_eval/g_eval.py)

[任务注册/配置](examples\finance_eval\tasks.py)

[运行](examples\finance_eval\run_eval.py)

[prompt模板](deepeval/metrics/<指标>/templates/)
需要转换为中文;更改prompt内容后，需要重编译：```python scripts/compile_metric_templates.py```

context	:提供给模型的事实依据（无论来源）
retrieval_context:RAG 检索器实际返回的文档块（顺序敏感）
