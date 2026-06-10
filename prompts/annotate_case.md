# annotate_case · 医案体标注器

输入是一段已被路由为 case_record 的原文 span。重建单个患者诊疗时间线：

- patient_context: {surname?, age?, sex?, origin?}（原文有才填）。
- presentation_timeline: [{stage: 1起算整数, stage_label: 初诊/复诊/汗后, time_gap_note: 翌日/三剂后, features: [症候], pulse: [], tongue: []}]。
- physician_reasoning_extracted: [{stage, judgment}]（医家自述辨析）。
- interventions: [{stage, formula?, formula_id?, modification_note?, non_formula_intervention?}]。
- outcome: {result: 原文转归描述, result_category: 痊愈|好转|无效|恶化|死亡|失访/未载, outcome_reliability: "author_reported"}。
- 医案 gold answer 只是该医家判断，不是客观真理；不得从医案归纳普遍规则。

输出 JSON 字段：patient_context, presentation_timeline, physician_reasoning_extracted, interventions, outcome, school_tag, annotation_flags。
