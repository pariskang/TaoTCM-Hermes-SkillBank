# annotate_herb · 本草体标注器

输入是一段已被路由为 materia_medica 的原文 span。抽取单味药属性：

- herb_name: 药名。
- properties: {taste_original(味X), thermal_original(性X/温/寒), toxicity_original: 无毒|微毒|有毒|大毒|未明示}。
- functions: 功效动词短语列表。
- indications_original: 原文主治列表（主X、Y、Z 拆条）。
- safety_constraints: 仅当原文明示毒性/禁忌时输出 [{constraint, constraint_type: population|combination|dose_warning|condition|processing_required, source_type: 原文明示, evidence_level: E1, enforcement: hard_stop|soft_alert|passive_info}]。
- 不得由单味药主治反推辨证规则；不得把后世安全共识冒充原文。

输出 JSON 字段：herb_name, properties, functions, indications_original, safety_constraints, annotation_flags。
