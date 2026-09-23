# prompts-extraction-case_summary_0903_20260923_003

> 任务：**extraction/case_summary** · 生成时间 2026-09-23 15:03:45

以下为发给 judge 模型的提示词。所有请求 system 一律为无，user 即下方各模板原文；`{{ input }}` 为用户输入，`{{ actual_output }}` 为模型输出。

## 1. 事实忠实度

### user（generate_truths）

```
根据给定{% if multimodal %}摘录（文本与图片）{% else %}文本{% endif %}，生成{{ limit }}条可从该{% if multimodal %}摘录{% else %}文本{% endif %}推断出的事实陈述。{{ multimodal_instruction }}

这些事实陈述**必须语义连贯，不能断章取义、脱离原文上下文。**

示例：
示例文本：
“张三与李四因民间借贷纠纷申请诉前调解，申请调解金额 5 万元，双方协商达成一致，李四分两期偿还欠款。”
示例JSON：
{
  "truths": [
    "张三和李四的案件属于民间借贷纠纷。",
    "张三就该民间借贷案件申请诉前调解。",
    "案件申请调解金额为5万元。",
    "张三李四双方协商达成调解方案。",
    "李四将分两期偿还欠款。"
  ]
}

===== 示例结束 =====

**重要提示：请确保仅返回 JSON 格式，key为truths，值为字符串列表，不要额外文字与解释。**
只提取原文内记载的事实陈述，**无需判断该陈述本身在现实世界是否真实，只忠实原文内容即可。**

{% if multimodal %}节选内容{% else %}文本{% endif %}：
{{ retrieval_context }}
JSON：
```

### user（generate_claims）

```
根据给定{% if multimodal %}摘录{% else %}文本{% endif %}，提取完整的、客观无争议的事实主张列表，主张从AI模型的输出内容中推断得出。{{ multimodal_instruction }}

提取的主张**必须语义连贯，不可断章取义、脱离原文上下文。**

示例：
示例文本：
“张三、李四因民间借贷纠纷申请诉前调解，双方协商确定调解金额 5 万元，李四承诺分两期归还。”
示例JSON：
{
  "claims": [
    "张三与李四存在民间借贷纠纷。",
    "张三李四就该民间借贷纠纷申请诉前调解。",
    "双方协商确定调解金额为5万元。",
    "李四承诺分两期归还该笔款项。"
  ]
}
===== 示例结束 =====

**重要：仅返回JSON格式，key为claims，值为字符串列表，不要额外文字与解释。**
仅提取文本内记载的主张，**不需要判断主张在现实世界是否真实**。提取主张时需要保留完整上下文，不能只截取片段信息。
禁止引入外部常识，提取主张仅按文本字面内容处理。
请注意，这些主张是AI模型输出的内容。

{% if multimodal %}节选内容{% else %}AI模型输出{% endif %}：
{{ actual_output }}
JSON：
```

### user（generate_verdicts）

```
根据给定的判定字符串列表，生成JSON对象列表，判断**每一条判定**是否与检索上下文里的事实存在矛盾。JSON包含两个字段：`verdict` 和 `reason`。

`verdict` 的取值**严格只能是** `yes`、`no`、`idk`，用来标记该判定是否与上下文内容相符。
仅当判定结果为 `no` 或者 `idk` 时，才填写`reason`理由。
这些判定取自AI模型实际输出。如果判定存在冲突，请在理由中利用检索上下文的事实给出修正内容。
{{ _fragments.faithfulness_verdicts_format_instruction }}
{% if multimodal %}{{ _fragments.faithfulness_verdicts_example_multimodal }}{% endif %}

**重要：请用中文回答，且仅返回JSON格式，顶层key为verdicts，值是JSON对象数组。**
{% if multimodal %}{{ _fragments.faithfulness_verdicts_guidelines_multimodal }}{% endif %}{% if not multimodal %}{{ _fragments.faithfulness_verdicts_guidelines_text_only }}{% endif %}

检索上下文：
{{ retrieval_context }}
判定列表：
{{ claims }}
JSON：
```

## 2. 回答相关性

### user（generate_statements）

```
给定文本，拆解并提取其中包含的陈述语句列表。模糊表述、单个词语，如果不属于完整连贯语句内部，也可单独作为一条陈述。

示例：
示例文本：
我们新款笔记本搭载高分辨率视网膜显示屏，画面清晰。配备快充电池，单次充电最长可使用12小时。安全方面增加指纹认证与加密固态硬盘。此外，每次购买附赠一年质保以及7×24小时客服支持。
{% if multimodal %}{{ _fragments.multimodal_input_rules }}{% endif %}
{
  "statements": [
    "张三与李四属于民间借贷纠纷。",
    "案件申请调解金额为5万元。",
    "双方达成调解协议。",
    "李四将分两期进行还款。"
  ]
}

===== 示例结束 =====

**重要提示：请确保仅返回有效且可解析的合法 JSON 格式，key为statements，值为字符串数组，不要额外文字解释。确保所有字符串都正确闭合。在输出前修复任何无效的 JSON。**

文本：
{{ actual_output }}
JSON：
```

### user（generate_verdicts）

```
针对给出的陈述列表，判断每一条陈述是否有助于解答输入问题。
生成JSON对象，包含 `verdict` 和 `reason` 两个字段。
`verdict` 的取值为 `yes`（相关）、`no`（无关）、`idk`（表述模糊/辅助参考信息）。
**仅当 verdict 为 no 或者 idk 时，才填写 reason。**
这些陈述来自AI模型的实际输出内容。
{% if multimodal %}{{ _fragments.multimodal_input_rules }}{% endif %}

**重要：请用中文回答，且仅返回合法可解析的JSON，顶层key为verdicts，值是JSON对象数组。保证所有字符串引号闭合，输出前修复JSON语法错误。**

预期JSON格式：
{
  "verdicts": [
    {
      "verdict": "yes"
    },
    {
      "reason": "无关原因说明",
      "verdict": "no"
    },
    {
      "reason": "模糊表述原因说明",
      "verdict": "idk"
    }
  ]
}

每条陈述生成一条判定结果，verdicts数组长度**必须**与陈述列表长度完全一致。
verdict**严格只能是** yes / no / idk：
- yes：陈述和用户输入问题相关，有助于回答输入
- no：陈述和用户输入问题无关
- idk：陈述语义模糊，不直接回答问题，但可作为辅助参考信息

仅在 verdict 为 no 或 idk 的时候填写 reason。

输入：
{{ input }}
陈述列表：
{{ statements }}
JSON：
```

## 3. 方案承诺演变履约链完整度

### user（generate_evaluation_steps）

```
给定评估标准，该标准规定了应如何对 {{ parameters }} 进行判断，基于下方标准生成3~4条简洁的评估步骤。**必须清晰说明如何对比各个{{ parameters }}之间的关系进行评估。**
{% if multimodal %}{{ _fragments.multimodal_input_rules }}{% endif %}

评估标准：
检查plan_feedback_and_commitments是否完整还原了当事人的承诺演变与履约链路，仅包含当事人承诺，不包含其他内容：1. 是否完整提取每一轮承诺、承诺修改、履约时间节点；2. 是否遗漏关键承诺变更；3. 是否编造对话不存在的承诺内容；4. 是否错误合并多轮不同承诺，扭曲演变顺序；5.若输入材料中不存在任何承诺链，则该字段采用上一轮的plan_feedback_and_commitments或不输出任何内容，填入臆造内容为错误；5.评估时先判断演变链是否存在，再评完整度。

**重要提示：仅返回JSON格式，key为steps，值为字符串列表，不要额外文字与解释。**
示例JSON：
{
  "steps": <list_of_strings>
}

JSON：
```

### user（generate_evaluation_results）

```
你是一名评估裁判。给定以下{% if rubric %}评估步骤与评分细则{% else %}评估步骤{% endif %}，对下方模型回答进行打分，返回一个包含两个字段的JSON对象：
- `"score"`：整数，取值范围在 {{ score_range[0] }} 至 {{ score_range[1] }} 之间。{% if rubric %}依据提供的评分细则判定{% else %}其中{{ score_range[1] }}代表高度符合评估步骤，{{ score_range[0] }}代表完全不符合{% endif %}。
- `"reason"`：对给出该分数原因的简要解释。理由必须指出具体优点或不足，引用输入中的相关细节。**解释中不得引用分数本身。**

理由需要满足：
- {% if rubric %}基于评估步骤和评分细则，描述要具体。{% else %}基于评估步骤，描述要具体。{% endif %}
- 引用测试用例参数中的关键信息。
- 简明清晰，并专注于评估逻辑。
{% if multimodal %}{{ _fragments.multimodal_input_rules }}{% endif %}

请用中文回答，且仅返回合法JSON，不要包含任何额外的评论或文字。
---
评估步骤：
{{ evaluation_steps }}
{% if rubric %}评分细则：
{{ rubric }}
{% endif %}测试用例：
{{ test_case_content }}
参数：
{{ parameters }}
{% if _additional_context %}
附加上下文：
{{ _additional_context }}
{% endif %}
---
**示例JSON：**
{
  "reason": "在此处填写简洁详实的理由",
  "score": {{ score_range[0] }}
}
JSON：
```

## 4. 调解抓手博弈价值度

### user（generate_evaluation_steps）

```
给定评估标准，该标准规定了应如何对 {{ parameters }} 进行判断，基于下方标准生成3~4条简洁的评估步骤。**必须清晰说明如何对比各个{{ parameters }}之间的关系进行评估。**
{% if multimodal %}{{ _fragments.multimodal_input_rules }}{% endif %}

评估标准：
评估mediation_levers提炼的调解抓手是否具有博弈价值：抓手应指向可实际施压或促成让步的信息（如失业可申请分期、逾期时长影响征信、对方有还款意愿但缺能力），而非空泛表述（如'加强沟通'、'保持联系'）。有价值的抓手应说明其可运用方向；case_info信息本身不作为调解抓手；输入中无可用抓手时采用上一轮的mediation_levers或不输出任何内容。

**重要提示：仅返回JSON格式，key为steps，值为字符串列表，不要额外文字与解释。**
示例JSON：
{
  "steps": <list_of_strings>
}

JSON：
```

### user（generate_evaluation_results）

```
你是一名评估裁判。给定以下{% if rubric %}评估步骤与评分细则{% else %}评估步骤{% endif %}，对下方模型回答进行打分，返回一个包含两个字段的JSON对象：
- `"score"`：整数，取值范围在 {{ score_range[0] }} 至 {{ score_range[1] }} 之间。{% if rubric %}依据提供的评分细则判定{% else %}其中{{ score_range[1] }}代表高度符合评估步骤，{{ score_range[0] }}代表完全不符合{% endif %}。
- `"reason"`：对给出该分数原因的简要解释。理由必须指出具体优点或不足，引用输入中的相关细节。**解释中不得引用分数本身。**

理由需要满足：
- {% if rubric %}基于评估步骤和评分细则，描述要具体。{% else %}基于评估步骤，描述要具体。{% endif %}
- 引用测试用例参数中的关键信息。
- 简明清晰，并专注于评估逻辑。
{% if multimodal %}{{ _fragments.multimodal_input_rules }}{% endif %}

请用中文回答，且仅返回合法JSON，不要包含任何额外的评论或文字。
---
评估步骤：
{{ evaluation_steps }}
{% if rubric %}评分细则：
{{ rubric }}
{% endif %}测试用例：
{{ test_case_content }}
参数：
{{ parameters }}
{% if _additional_context %}
附加上下文：
{{ _additional_context }}
{% endif %}
---
**示例JSON：**
{
  "reason": "在此处填写简洁详实的理由",
  "score": {{ score_range[0] }}
}
JSON：
```

## 5. 高敏合规与客诉风险捕获率

### user（generate_evaluation_steps）

```
给定评估标准，该标准规定了应如何对 {{ parameters }} 进行判断，基于下方标准生成3~4条简洁的评估步骤。**必须清晰说明如何对比各个{{ parameters }}之间的关系进行评估。**
{% if multimodal %}{{ _fragments.multimodal_input_rules }}{% endif %}

评估标准：
评估 risk_items 对高风险信号的捕获完整度。必查信号：当事人情绪激烈/辱骂（客诉风险）、身份存疑或冒用（合规风险）、提及投诉/媒体/诉讼（升级风险）、泄露无关第三人信息（隐私合规）。输入中存在但输出遗漏的信号计为漏捕；无中生有的风险项计为误报；在模型输出其他字段提及的信息不作为风险信号；输入中无风险信号时模型实际输出完全置空。

**重要提示：仅返回JSON格式，key为steps，值为字符串列表，不要额外文字与解释。**
示例JSON：
{
  "steps": <list_of_strings>
}

JSON：
```

### user（generate_evaluation_results）

```
你是一名评估裁判。给定以下{% if rubric %}评估步骤与评分细则{% else %}评估步骤{% endif %}，对下方模型回答进行打分，返回一个包含两个字段的JSON对象：
- `"score"`：整数，取值范围在 {{ score_range[0] }} 至 {{ score_range[1] }} 之间。{% if rubric %}依据提供的评分细则判定{% else %}其中{{ score_range[1] }}代表高度符合评估步骤，{{ score_range[0] }}代表完全不符合{% endif %}。
- `"reason"`：对给出该分数原因的简要解释。理由必须指出具体优点或不足，引用输入中的相关细节。**解释中不得引用分数本身。**

理由需要满足：
- {% if rubric %}基于评估步骤和评分细则，描述要具体。{% else %}基于评估步骤，描述要具体。{% endif %}
- 引用测试用例参数中的关键信息。
- 简明清晰，并专注于评估逻辑。
{% if multimodal %}{{ _fragments.multimodal_input_rules }}{% endif %}

请用中文回答，且仅返回合法JSON，不要包含任何额外的评论或文字。
---
评估步骤：
{{ evaluation_steps }}
{% if rubric %}评分细则：
{{ rubric }}
{% endif %}测试用例：
{{ test_case_content }}
参数：
{{ parameters }}
{% if _additional_context %}
附加上下文：
{{ _additional_context }}
{% endif %}
---
**示例JSON：**
{
  "reason": "在此处填写简洁详实的理由",
  "score": {{ score_range[0] }}
}
JSON：
```

## 6. 增量更新与上下文一致性

### user（generate_evaluation_steps）

```
给定评估标准，该标准规定了应如何对 {{ parameters }} 进行判断，基于下方标准生成3~4条简洁的评估步骤。**必须清晰说明如何对比各个{{ parameters }}之间的关系进行评估。**
{% if multimodal %}{{ _fragments.multimodal_input_rules }}{% endif %}

评估标准：
检查 actual_output 中的case_brief、key_communication_facts.party_basic_information、key_communication_facts.core_demands是否正确融合了的新进展，不检查未提及字段。对比 existing_case_overview，看历史核心结论是否被合理保留或更新，没有无故丢失关键信息，也没有将历史未发生的事当成现状。仅需从dialogue_text提取新增内容，其他字段皆只用来辅助判断；且已经知晓案件基本信息（例如申请人、平台、阶段、纠纷类型、标的、逾期天数等），无需模型从输入中提取和新增。

**重要提示：仅返回JSON格式，key为steps，值为字符串列表，不要额外文字与解释。**
示例JSON：
{
  "steps": <list_of_strings>
}

JSON：
```

### user（generate_evaluation_results）

```
你是一名评估裁判。给定以下{% if rubric %}评估步骤与评分细则{% else %}评估步骤{% endif %}，对下方模型回答进行打分，返回一个包含两个字段的JSON对象：
- `"score"`：整数，取值范围在 {{ score_range[0] }} 至 {{ score_range[1] }} 之间。{% if rubric %}依据提供的评分细则判定{% else %}其中{{ score_range[1] }}代表高度符合评估步骤，{{ score_range[0] }}代表完全不符合{% endif %}。
- `"reason"`：对给出该分数原因的简要解释。理由必须指出具体优点或不足，引用输入中的相关细节。**解释中不得引用分数本身。**

理由需要满足：
- {% if rubric %}基于评估步骤和评分细则，描述要具体。{% else %}基于评估步骤，描述要具体。{% endif %}
- 引用测试用例参数中的关键信息。
- 简明清晰，并专注于评估逻辑。
{% if multimodal %}{{ _fragments.multimodal_input_rules }}{% endif %}

请用中文回答，且仅返回合法JSON，不要包含任何额外的评论或文字。
---
评估步骤：
{{ evaluation_steps }}
{% if rubric %}评分细则：
{{ rubric }}
{% endif %}测试用例：
{{ test_case_content }}
参数：
{{ parameters }}
{% if _additional_context %}
附加上下文：
{{ _additional_context }}
{% endif %}
---
**示例JSON：**
{
  "reason": "在此处填写简洁详实的理由",
  "score": {{ score_range[0] }}
}
JSON：
```

## 7. 调解员使用友好度

### user（generate_evaluation_steps）

```
给定评估标准，该标准规定了应如何对 {{ parameters }} 进行判断，基于下方标准生成3~4条简洁的评估步骤。**必须清晰说明如何对比各个{{ parameters }}之间的关系进行评估。**
{% if multimodal %}{{ _fragments.multimodal_input_rules }}{% endif %}

评估标准：
你是一名资深债务纠纷调解员，不检查内容是否真实、有无法律错误，你只评估：这份模型输出，调解员办案时好不好用，能不能辅助调解准备、减少整理案情的工作量。

**重要提示：仅返回JSON格式，key为steps，值为字符串列表，不要额外文字与解释。**
示例JSON：
{
  "steps": <list_of_strings>
}

JSON：
```

### user（generate_evaluation_results）

```
你是一名评估裁判。给定以下{% if rubric %}评估步骤与评分细则{% else %}评估步骤{% endif %}，对下方模型回答进行打分，返回一个包含两个字段的JSON对象：
- `"score"`：整数，取值范围在 {{ score_range[0] }} 至 {{ score_range[1] }} 之间。{% if rubric %}依据提供的评分细则判定{% else %}其中{{ score_range[1] }}代表高度符合评估步骤，{{ score_range[0] }}代表完全不符合{% endif %}。
- `"reason"`：对给出该分数原因的简要解释。理由必须指出具体优点或不足，引用输入中的相关细节。**解释中不得引用分数本身。**

理由需要满足：
- {% if rubric %}基于评估步骤和评分细则，描述要具体。{% else %}基于评估步骤，描述要具体。{% endif %}
- 引用测试用例参数中的关键信息。
- 简明清晰，并专注于评估逻辑。
{% if multimodal %}{{ _fragments.multimodal_input_rules }}{% endif %}

请用中文回答，且仅返回合法JSON，不要包含任何额外的评论或文字。
---
评估步骤：
{{ evaluation_steps }}
{% if rubric %}评分细则：
{{ rubric }}
{% endif %}测试用例：
{{ test_case_content }}
参数：
{{ parameters }}
{% if _additional_context %}
附加上下文：
{{ _additional_context }}
{% endif %}
---
**示例JSON：**
{
  "reason": "在此处填写简洁详实的理由",
  "score": {{ score_range[0] }}
}
JSON：
```
