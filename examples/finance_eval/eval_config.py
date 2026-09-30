"""评估配置：集中管理 judge 模型与数据集/标准文件路径。

模型 key 等敏感信息放 .env.local（已被 .gitignore 忽略）。
切换 judge 模型只改 JUDGE_MODEL 一行（或用 .env.local 的 JUDGE_PROVIDER）。
"""

import os

from deepeval.models import OpenAIModel


def _mk(model_env, model_default, base_env, base_default, key_env, label):
    """构建 OpenAI 兼容模型；key 为空时返回 None 并警告。"""
    key = os.getenv(key_env)
    if not key:
        print(f"⚠ [{label}] {key_env} 未配置（.env.local），该模型不可用")
        return None
    return OpenAIModel(
        model=os.getenv(model_env, model_default),
        base_url=os.getenv(base_env, base_default),
        api_key=key,
    )


# ---------------- 可用 judge 模型注册 ----------------

_MODELS = {
    # DeepSeek-V4-Flash 正式版（火山方舟 ark API，OpenAI 兼容）
    # 默认 judge：.env.local 未配 JUDGE_PROVIDER 时走这个
    "deepseek_v4_flash": lambda: _mk(
        "DEEPSEEK_MODEL_ID", "deepseek-v4-flash-ga-260731",
        "DEEPSEEK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3",
        "DEEPSEEK_API_KEY", "deepseek",
    ),
    # DeepSeek-V4-Pro 正式版（同 key，旗舰档，打分一致性预期最好）
    "deepseek_v4_pro": lambda: _mk(
        "DEEPSEEK_PRO_MODEL_ID", "deepseek-v4-pro-ga-260813",
        "DEEPSEEK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3",
        "DEEPSEEK_API_KEY", "deepseek",
    ),
    # 豆包 Seed 2.1 Pro（火山方舟 ark API，OpenAI 兼容）
    # 也可用直连模型 ID：doubao-seed-2-1-pro-260915
    "doubao_seed_2_1_pro": lambda: _mk(
        "DOUBAO_S21_MODEL_ID", "doubao-seed-2-1-pro-260915",
        "DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3",
        "DOUBAO_API_KEY", "doubao",
    ),
    # 豆包 Seed 1.6（火山方舟 ark API；model 填推理接入点 ID）
    # hz_doubao_seed_1.6 接入点：ep-20250617155424-hjcnp，key 待填 DOUBAO_API_KEY
    "hz_doubao_seed_1.6": lambda: _mk(
        "DOUBAO_MODEL_ID", "ep-20250617155424-hjcnp",
        "DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3",
        "DOUBAO_API_KEY", "doubao",
    ),
    # ChatGLM Code 版（OpenAI 兼容接口）
    "glm": lambda: _mk(
        "GLM_MODEL_NAME", "glm-5",
        "GLM_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4",
        "GLM_API_KEY", "glm",
    ),
}

# 当前 judge 模型：.env.local 的 JUDGE_PROVIDER 选择
# （deepseek_v4_flash / deepseek_v4_pro /
#  doubao_seed_2_1_pro / hz_doubao_seed_1.6 / glm）
PROVIDER = os.getenv("JUDGE_PROVIDER", "deepseek_v4_flash")
JUDGE_MODEL = _MODELS[PROVIDER]()
