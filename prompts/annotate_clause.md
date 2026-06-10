# annotate_clause · 经论条文体标注器

输入是一段已被路由为 canonical_clause 的原文 span。抽取条文级结构：

- clause_subtype: prescriptive（条件→处置）| theoretical（条件→病机/病名判定）| contraindication（禁律）| mistreatment_consequence（误治后果）。
- states: 病位/病名前提（如 太阳病、太阳中风、伤寒）。
- features_present: 原文明示存在的症候特征（保留原文词形）。
- features_absent: 原文明示不存在的特征（不汗出→无汗、不渴）。
- compound_features: 并见才有意义的组合（如 无汗而喘 → components [无汗, 喘]），推理时不可拆开计分。
- or_features: 或然症（或渴或不渴）。
- treatment_context: 治疗史前提（已发汗、下之后）。course_context: 病程前提（得之X日）。
- pulse_features: 脉象原文词形（脉浮紧 整体保留，归一化在下游）。
- conclusion: {type: formula|treatment_method|pattern_naming|prohibition|prognosis, formula?, treatment_method?, pattern_name?, assertion_force: 主之|宜|可与|可|当|不可与|不可|禁|与之则|宜先|宜后|未明示}。
- negative_clause: 同条内禁忌/反面内容（condition, assertion_force, consequence, risk_tier）。
- risk_tier: 禁忌/误治类一律 T3；处方规则 T2；理论条文 T1。

输出 JSON 字段：clause_subtype, states, features_present, features_absent, compound_features, or_features, treatment_context, course_context, pulse_features, conclusion, negative_clause(可省), annotation_flags(数组)。
