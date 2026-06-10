# annotate_formula · 方书体标注器

输入是一段已被路由为 formula_entry 的原文 span。抽取方剂档案：

- formula_name: 方名（若 span 内无方名，从上下文行推断，并在 annotation_flags 加 "formula_name_from_context"）。
- composition: [{herb, dose_original, processing_note?}]，剂量保留原文（三两/七十枚），**禁止换算现代克数**。
- preparation: 煎法原文摘录（以水X升，煮取X升，去滓）。
- administration: 服法将息（温服X合，覆取微似汗，禁生冷）。
- modification_rules: [{condition, add: [{herb, dose_original?}], remove: [herb], note?}]（若渴者去X加Y）。
- expected_response: 药后预期反应（微似汗/一服愈）。

输出 JSON 字段：formula_name, composition, preparation, administration, modification_rules, expected_response, annotation_flags。
