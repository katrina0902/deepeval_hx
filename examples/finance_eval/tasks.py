"""两层任务注册表：大类(category) → AI任务(task)。

- 大类：一组同类 AI 任务共享的评估配置。定义于 examples/finance_eval/categories/<大类>.yaml
  （通用指标 + LLMTestCase 字段约定 + evaluate 参数 + Python 专有参数关联）。
- 任务：大类下的具体 AI 功能（如"案情概览"）。每个任务一份
  examples/finance_eval/categories/<大类>/<任务>.yaml，维护自己的自定义 GEval；
  数据在 examples/finance_eval/data/<大类>/<任务>.csv。

注册新任务三步：
1. data/<大类>/ 放 <任务>.csv
2. categories/<大类>/ 放 <任务>.yaml（该任务专属 GEval，可为空文件）
3. 在 TASKS 里注册一行

注册新大类三步：
1. categories/ 放 <大类>.yaml（含 meta 与通用指标）
2. 建目录 data/<大类>/ 和 categories/<大类>/
3. 在 CATEGORIES 里注册一行
"""

import os

from pydantic import BaseModel

_EVALS_DIR = os.path.dirname(__file__)

# ---------- Python 专有参数（YAML 表达不了的），按大类维护 ----------

class CaseBrief(BaseModel):
    """信息提取大类：案情摘要的期望输出结构（json_correctness 用）。"""
    case_brief: str
    key_communication_facts: dict


class ContactRecord(BaseModel):
    """信息提取大类：历史记录的期望输出结构。"""
    contact_time: str
    contacted_party: str
    result: str
    next_action: str


EXTRA_PARAMS = {
    "extraction": {
        # 各任务可复用/各配一份 schema
        "case_summary": {"json_schema": CaseBrief},
        "contact_record": {"json_schema": ContactRecord},
    },
    # 生成类：Python 专有参数（如需）
    "generation": {},
    # 判断类
    "judgment": {},
}


# ---------- 大类注册表 ----------

CATEGORIES = {
    "extraction": {
        "desc": "信息提取：从案件材料/沟通记录提取结构化信息",
        "config": os.path.join(_EVALS_DIR, "categories", "extraction.yaml"),
    },
    "generation": {
        "desc": "生成：调解话术/案情简述等文本生成",
        "config": os.path.join(_EVALS_DIR, "categories", "generation.yaml"),
    },
    "judgment": {
        "desc": "判断：沟通有效性/风险等级等分类判定",
        "config": os.path.join(_EVALS_DIR, "categories", "judgment.yaml"),
    },
}


# ---------- 任务注册表（key = "大类/任务"） ----------

TASKS = {
    # ===== 信息提取大类 =====
    "extraction/case_summary": {
        "desc": "案情概览：data/files 导出 CSV，按 ai_task 筛选",
        "data": os.path.join(_EVALS_DIR, "data", "files", "案情概览testcase.csv"),
        "criteria": os.path.join(_EVALS_DIR, "categories", "extraction", "case_summary.yaml"),
        # 默认采样条数：每次运行最多取前 N 条；留空/不配 → 取全部
        # （命令行 --limit N 可覆盖该默认值）
        "limit": 1000,
        # 外部导出 CSV 列名 → LLMTestCase 字段/元数据的映射
        "columns": {
            "ai_task": "案情概览",            # 只取该 ai_task 的行
            "input": "input_text",            # 用户输入列
            "actual_output": "ai_response_content",  # 模型输出列
            "case_id": "case_id",             # 报告展示列
            "trigger_time": "trigger_time",   # 报告展示列
        },
    },

    "extraction/contact_record": {
        "desc": "联系记录提取：从通话记录提取联系结果与后续动作",
        "data": os.path.join(_EVALS_DIR, "data", "extraction", "contact_record.csv"),
        "criteria": os.path.join(_EVALS_DIR, "categories", "extraction", "contact_record.yaml"),
    },
    # ===== 生成大类 =====
    "generation/mediation_script": {
        "desc": "调解话术生成：面向被申请人的沟通话术",
        "data": os.path.join(_EVALS_DIR, "data", "generation", "mediation_script.csv"),
        "criteria": os.path.join(_EVALS_DIR, "categories", "generation", "mediation_script.yaml"),
    },
    # ===== 判断大类 =====
    "judgment/communication_validity": {
        "desc": "沟通有效性判定：判断一次外呼是否有效沟通",
        "data": os.path.join(_EVALS_DIR, "data", "judgment", "communication_validity.csv"),
        "criteria": os.path.join(_EVALS_DIR, "categories", "judgment", "communication_validity.yaml"),
    },
}


def tasks_in_category(category: str) -> list:
    return [k for k in TASKS if k.split("/")[0] == category]
