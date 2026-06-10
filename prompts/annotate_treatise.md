# annotate_treatise · 医论体标注器

输入是一段已被路由为 treatise 的原文 span。抽取主张（claim），不是规则（rule）：

- claim_type: pathogenesis_principle|transmission_framework|treatment_principle|physiology_doctrine|diagnostic_principle|ethics_or_practice_norm。
- claims: [{subject, predicate, object, condition?, quantifier: universal|typical|conditional|unspecified}]——“诸X皆属于Y”为 universal，universal 主张默认仅作病机解释候选，**禁止编译为硬匹配规则**。
- transmission_states: [{from_state, to_state, pathway_type: 顺传|逆传|误治变证|未明示}]（传变框架才填）。
- school_tag: 流派归属。

输出 JSON 字段：claim_type, claims, transmission_states, school_tag, annotation_flags。
