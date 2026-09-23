from .base_metric import (
    BaseMetric,
    BaseConversationalMetric,
    BaseArenaMetric,
)

from .dag.dag import DAGMetric, DeepAcyclicGraph
from .conversational_dag.conversational_dag import ConversationalDAGMetric
from .bias.bias import BiasMetric
from .exact_match.exact_match import ExactMatchMetric
from .pattern_match.pattern_match import PatternMatchMetric
from .toxicity.toxicity import ToxicityMetric
from .pii_leakage.pii_leakage import PIILeakageMetric
from .non_advice.non_advice import NonAdviceMetric
from .misuse.misuse import MisuseMetric
from .role_violation.role_violation import RoleViolationMetric
from .hallucination.hallucination import HallucinationMetric
from .answer_relevancy.answer_relevancy import AnswerRelevancyMetric
from .summarization.summarization import SummarizationMetric
from .g_eval.g_eval import GEval, GEvalTemplate
from .arena_g_eval.arena_g_eval import ArenaGEval
from .faithfulness.faithfulness import FaithfulnessMetric
from .contextual_recall.contextual_recall import ContextualRecallMetric
from .contextual_relevancy.contextual_relevancy import ContextualRelevancyMetric
from .contextual_precision.contextual_precision import ContextualPrecisionMetric
from .knowledge_retention.knowledge_retention import KnowledgeRetentionMetric
from .tool_correctness.tool_correctness import ToolCorrectnessMetric
from .tool_permission.tool_permission import ToolPermissionMetric
from .json_correctness.json_correctness import JsonCorrectnessMetric
from .prompt_alignment.prompt_alignment import PromptAlignmentMetric
from .task_completion.task_completion import TaskCompletionMetric
from .topic_adherence.topic_adherence import TopicAdherenceMetric
from .step_efficiency.step_efficiency import StepEfficiencyMetric
from .plan_adherence.plan_adherence import PlanAdherenceMetric
from .plan_quality.plan_quality import PlanQualityMetric
from .tool_use.tool_use import ToolUseMetric
from .goal_accuracy.goal_accuracy import GoalAccuracyMetric
from .argument_correctness.argument_correctness import ArgumentCorrectnessMetric
from .agent_loop_detection.agent_loop_detection import AgentLoopDetectionMetric
from .mcp.mcp_task_completion import MCPTaskCompletionMetric
from .mcp.multi_turn_mcp_use_metric import MultiTurnMCPUseMetric
from .mcp_use_metric.mcp_use_metric import MCPUseMetric
from .turn_relevancy.turn_relevancy import (
    TurnRelevancyMetric,
)
from .turn_faithfulness.turn_faithfulness import TurnFaithfulnessMetric
from .turn_contextual_precision.turn_contextual_precision import (
    TurnContextualPrecisionMetric,
)
from .turn_contextual_recall.turn_contextual_recall import (
    TurnContextualRecallMetric,
)
from .turn_contextual_relevancy.turn_contextual_relevancy import (
    TurnContextualRelevancyMetric,
)
from .conversation_completeness.conversation_completeness import (
    ConversationCompletenessMetric,
)
from .role_adherence.role_adherence import (
    RoleAdherenceMetric,
)
from .conversational_g_eval.conversational_g_eval import ConversationalGEval
from .multimodal_metrics import (
    TextToImageMetric,
    ImageEditingMetric,
    ImageCoherenceMetric,
    ImageHelpfulnessMetric,
    ImageReferenceMetric,
)
from .voice import (
    AgentResponsivenessMetric,
    AudioIntegrityMetric,
    SpeechIntelligibilityMetric,
    TurnTakingNaturalnessMetric,
    VoiceConsistencyMetric,
    VoiceNaturalnessMetric,
    VoiceReliabilityMetric,
)

__all__ = [
    # Base classes
    "BaseMetric",
    "BaseConversationalMetric",
    "BaseArenaMetric",
    
    # 非 LLM 确定性指标（本地计算，零成本）
    "ExactMatchMetric", #   实际输出与期望输出完全一致；需要字段input, actual_output, expected_output
    "PatternMatchMetric", # 输出是否匹配正则表达式；需要字段input, actual_output；专有参数pattern（必填，正则表达式字符串，fullmatch 匹配，如 r"\d{4}-\d{2}-\d{2}"）, ignore_case忽略大小写
    
    # 通用自定义指标
    "GEval",#   按任意自定义标准打分（论文级 LLM-as-judge，CoT+logprob加权）；需要字段evaluation_params自选；专有参数criteria 或 evaluation_steps 二选一、rubric 档位量规、top_logprobs
    "GEvalTemplate",
    "ArenaGEval",#  A/B 对比多个模型输出，选 winner（配合 compare()）；需要字段ArenaTestCase；专有参数criteria
    "ConversationalGEval",# 同"GEval"，多轮对话版；需要字段MultiTurnParams 自选；专有参数同"GEval"
    "DAGMetric",#按DAG 图编排多步评估流程（TaskNode/判定节点分支）；需要字段图节点自定；专有参数dag: DeepAcyclicGraph 必填
    "DeepAcyclicGraph",
    "ConversationalDAGMetric",# 同"DAGMetric"，多轮对话版；需要字段多轮	；专有参数同"DAGMetric"
    
    # RAG 指标（需要检索上下文）
    "AnswerRelevancyMetric",#输出是否回应了问题；需要字段input, actual_output
    "FaithfulnessMetric",#输出事实是否忠于检索文档	input, actual_output, retrieval_context
    "ContextualRecallMetric",#检索结果能否覆盖期望答案	input, retrieval_context, expected_output
    "ContextualRelevancyMetric",#检索结果整体相关度	input, retrieval_context
    "ContextualPrecisionMetric",#检索结果排序质量（相关的是否排前）	input, retrieval_context, expected_output
    
    # MCP metrics
    "MCPTaskCompletionMetric",#多轮 MCP 辅助任务完成度；需要字段turns + mcp_servers 必填
    "MultiTurnMCPUseMetric",#多轮 MCP 原语选择+参数准确性	turns + mcp_servers 必填
    "MCPUseMetric",#单轮 MCP 原语（tools/resources/prompts）使用恰当性	input, actual_output, mcp_servers 必填
    
    # 内容质量
    "HallucinationMetric",# 输出是否与参考事实矛盾（1=无幻觉）需要字段input, actual_output, context
    "BiasMetric",#  性别/种族/政治偏见（1=无）；需要字段input, actual_output
    "ToxicityMetric",#  毒性攻击性内容（1=无毒）；需要字段input, actual_output
    "SummarizationMetric",# 摘要覆盖度+对齐度；需要字段input(原文), actual_output(摘要)；专有参数assessment_questions 自定义问题、n=问题数（不给问题清单时自动生成几个问题（默认 5）
    
    # 安全合规
    "PIILeakageMetric",#  隐私信息泄露（1=无）	input, actual_output
    "NonAdviceMetric",# 是否规避了特定领域建议（1=合规）	input, actual_output	禁止建议的领域：advice_types=['financial','medical',...] 必填
    "MisuseMetric",#是否属于指定 domain 的滥用（1=无）	input, actual_output	；domain 必填 检测滥用的领域："cybersecurity"
    "RoleViolationMetric",# 是否违反角色设定（二值）	input, actual_output	role 必填（期望角色描述）
    "ToolPermissionMetric",#调用的工具是否在授权白名单内；需要字段tools_called；allowed_tools（授权白名单：["search_web", "query_db"]）/denied_tools（禁用黑名单（与白名单至少填一个）） 至少一个
    "RoleAdherenceMetric",#（用例上）chatbot_role	填在 ConversationalTestCase(chatbot_role=...)，不是指标参数
    
    # 任务指标
    "ToolCorrectnessMetric",#   调用的工具对不对（含参数顺序匹配，主分确定性）	input, tools_called, expected_tools	追踪：否 （available_tools	全量工具清单（启用 LLM 辅助“选型是否合理”加分项）；should_exact_match	工具+参数必须完全一致（默认 False）；should_consider_ordering	是否考虑调用顺序（LCS 加权）；evaluation_params	参与比较的工具要素：[ToolCallParams.INPUT_PARAMETERS, ToolCallParams.OUTPUT]）
    "JsonCorrectnessMetric",#   输出 JSON 是否符合 Pydantic schema（校验确定性0/1，解释用LLM）	input, actual_output	expected_schema: BaseModel（Pydantic 模型类（不是实例）：expected_schema=CaseSummary） 必填
    "PromptAlignmentMetric",#   输出是否遵守一组指令	input, actual_output	prompt_instructions: List[str] 必填，你的系统提示词里的指令列表（逐条检查遵守情况）
    "TaskCompletionMetric",#    Agent 是否完成用户任务	trace 优先，回退 input/actual_output	是	trace 优先，回退 input/actual_output	追踪：是；task	显式指定任务描述；不填则从 trace/input 自动提取
    "ArgumentCorrectnessMetric",#   工具入参是否正确	input, tools_called	追踪：否
    "KnowledgeRetentionMetric",#是否记住早前说过的信息
    
    # agent指标
    "TopicAdherenceMetric",#    是否守住主题边界（precision/recall/f1）	relevant_topics 必填，主题白名单：["债务调解", "还款协商"]；指标算 precision/recall/f1
    "StepEfficiencyMetric",#    执行路径是否高效无冗余步骤	trace	追踪：是
    "PlanAdherenceMetric",#    是否遵循自己生成的计划	trace	追踪：是
    "PlanQualityMetric",#    计划本身的质量	trace	追踪：是
    "ToolUseMetric",#多轮下工具选择与用法（选择分×参数分）	turns + available_tools（必填：多轮场景下可供选择的工具全集） 必填	追踪：多轮
    "GoalAccuracyMetric",# 多轮中每个用户目标达成度	turns	追踪：多轮
    "AgentLoopDetectionMetric",#    Agent 是否陷入死循环（工具重复/推理停滞/调用图成环）；需要字段trace；专有参数repetition_threshold（同一工具重复调用几次算循环（默认 3））, similarity_threshold（推理文本相似度超过多少算停滞（默认 0.85）；；check_tool_repetition / check_reasoning_stagnation / check_call_graph_cycles	三种检测开关，按需关闭
    
    # 对话指标 （Turn 系列多轮指标	window_size	滑动窗口轮数（默认 10，长对话评估粒度））
    "TurnRelevancyMetric",#每轮回复相关性
    "ConversationCompletenessMetric",
    "TurnFaithfulnessMetric",#每轮对检索的忠实度；额外需要Turn 级 retrieval_context；truths_extraction_limit	从检索文档最多抽取多少条事实（防长文档超 token）；penalize_ambiguous_claims	模糊表述是否扣分
    "TurnContextualPrecisionMetric",#每轮检索排序质量；额外需要+ expected_outcome
    "TurnContextualRecallMetric",#每轮检索覆盖度	+ expected_outcome
    "TurnContextualRelevancyMetric",#每轮检索相关度

    # 多模态 metrics （ImageCoherence 等	max_context_size	图片周围取多少文本做上下文）
    "TextToImageMetric",#文生图：语义一致+感知质量；图像要求input 0图 + output 1图
    "ImageEditingMetric",#图像编辑效果	input 1图（原图）+ output 1图
    "ImageCoherenceMetric",#图与上下文文本连贯性	output ≥1图
    "ImageHelpfulnessMetric",#图对理解文本的帮助度	output ≥1图
    "ImageReferenceMetric",#图是否被文本正确引用	output ≥1图

    # 语音指标
    "VoiceNaturalnessMetric",#语音自然度（语速/静音占比）
    "TurnTakingNaturalnessMetric",#轮换自然度（gap/打断/重叠）
    "SpeechIntelligibilityMetric",#语音可懂度（SNR/电平）
    "VoiceConsistencyMetric",#声音跨轮一致性（音高/音色）
    "AgentResponsivenessMetric",#Agent 是否响应每次用户发言（文本即可）
    "AudioIntegrityMetric",#音频完整性（缺失/削波/长静音）
    "VoiceReliabilityMetric",#可靠性总览（响应性+完整性各50%）
]
