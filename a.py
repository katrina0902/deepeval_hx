"""最小可执行评估单元：python a.py

- 模型：ChatGLM Code 版，key 在 .env.local（GLM_API_KEY / GLM_BASE_URL / GLM_MODEL_NAME）
- 报告：终端全量明细 + verbose 逐步日志 + HTML 报告 + JSON 结果文件
"""

import os

from deepeval.evaluate import evaluate, DisplayConfig, ErrorConfig
from deepeval.metrics import AnswerRelevancyMetric, GEval
from deepeval.models import OpenAIModel
from deepeval.test_case import LLMTestCase, SingleTurnParams

# ChatGLM Code 版（OpenAI 兼容接口），参数来自 .env.local
glm = OpenAIModel(
    model=os.getenv("GLM_MODEL_NAME", "glm-5"),
    base_url=os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4"),
    api_key=os.getenv("GLM_API_KEY"),
)

input_json = """{"case_info":{"subject_amount":"3277.84","loan_date":"","overdue_days":810,"debt_platform":"国美金融","applicant":"杭州云昇商业管理合伙企业（有限合伙）"},"previous_communication_summary":"","current_mediation_record":{"call_tag":"有效沟通","dialogue_text":"调解员：喂，\\n调解员：你好喂，\\n被申请人：谁呀你好你好，\\n调解员：你好，\\n调解员：请问是谢宋江吗？\\n被申请人：我是你爹，\\n调解员：我这边是南平仲裁委员会金融纠纷调解中心，\\n调解员：先跟你核实一下，\\n调解员：你是谢宋江本人吗？\\n被申请人：我是。\\n调解员：不好意思，\\n调解员：打扰了，\\n调解员：不是本人的话，\\n调解员：就不透露相关信息了，\\n调解员：再见。\\n","communication_time":"2026-09-10","communication_target_type":"本人","communication_type":"通话"},"existing_case_overview":{"key_communication_facts":{}}}"""

actual_output_json = """{
  "case_brief": "1、已联系上被申请人本人，但其态度抵触，尚未进入实质协商。\\n2、被申请人接通后言语不逊，沟通不畅，后续需关注其配合度及沟通风险。",
  "key_communication_facts": {
    "party_basic_information": "",
    "core_demands": "",
    "plan_feedback_and_commitments": "",
    "mediation_levers": "",
    "risk_items": "1、被申请人接通后以不逊言语回应，态度抵触，双方尚未进入实质沟通。"
  }
}"""

test_case = LLMTestCase(
    input=input_json,
    actual_output=actual_output_json,
    name="调解案件摘要-谢x江-20260910",
    tags=["调解", "案件摘要"],
)

metrics = [
    # 摘要是否回应了案件信息（对话内容、当事人等）
    AnswerRelevancyMetric(model=glm, threshold=0.7, include_reason=True),
    # 事实忠实性：摘要内容是否与原始对话记录一致，不得编造
    GEval(
        name="事实忠实性",
        criteria=(
            "判断摘要中的每项陈述是否都能从输入的案件信息和调解对话记录中找到依据。"
            "重点检查：案件金额、逾期天数、债权平台、被申请人身份、沟通状态描述是否与对话原文一致，"
            "任何对话中未出现的事实（如还款承诺、协商内容）都算编造。"
        ),
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
        model=glm,
        threshold=0.8,
        strict_mode=False,
    ),
    # 摘要完整性：关键字段是否遗漏了对话中的重要信息
    GEval(
        name="摘要完整性",
        criteria=(
            "判断摘要是否完整提炼了输入案件和对话记录中的关键信息，"
            "包括：案件基本信息（金额/逾期/平台）、沟通对象确认情况、被申请人态度、当前沟通进展、风险点。"
            "遗漏重要信息或关键事实字段留空且对话中有对应内容时扣分。"
        ),
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
        model=glm,
        threshold=0.7,
    ),
    # 输出规范：JSON 结构与字段是否符合案件摘要格式
    GEval(
        name="格式规范性",
        criteria=(
            "判断输出是否为结构规范的案件摘要 JSON："
            "包含 case_brief（案情简述）和 key_communication_facts（关键沟通事实）两部分，"
            "key_communication_facts 下应含 party_basic_information、core_demands、"
            "plan_feedback_and_commitments、mediation_levers、risk_items 字段；"
            "无信息时字段应留空而非缺失，不得出现格式错误或多余字段。"
        ),
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
        model=glm,
        threshold=0.8,
    ),
]

result = evaluate(
    test_cases=[test_case],
    metrics=metrics,
    identifier="调解案件摘要评估",
    display_config=DisplayConfig(
        show_indicator=True,              # 显示指标进度指示
        print_results=True,               # 终端打印完整结果表
        verbose_mode=True,                # 打印每个指标的完整中间步骤（statements/verdicts/评分理由）
        truncate_passing_cases=False,     # 通过的用例不截断，显示全部明细
        results_folder=".deepeval_results",      # 导出 test_run_<ts>.json（结构化结果）
        file_type="html",                 # 同时导出 HTML 报告
        file_output_dir=".deepeval_results",
        inspect_after_run=False,          # 脚本模式，结束后不进交互 TUI
    ),
    error_config=ErrorConfig(
        ignore_errors=True,               # 单指标失败不中断整体运行
        skip_on_missing_params=True,      # 指标缺参数时跳过而非报错
    ),
)

# result.test_results 内含每个指标的 score/reason/success，可按需二次处理
for tr in result.test_results:
    for md in tr.metrics_data:
        print(f"[{md.name}] score={md.score} success={md.success}")
        print(f"  reason: {md.reason}\n")
