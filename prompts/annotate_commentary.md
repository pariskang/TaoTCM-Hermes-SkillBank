# annotate_commentary · 注释体标注器

输入是一段已被路由为 commentary 的注语 span（被注原文已切出为独立 span）。

- commentator: {name, school_tag?}（注家署名；无法判定填 "未署名"）。
- interpretation_type: 训诂|病机阐释|方义阐释|校勘|驳议|临证发挥。
- interpretation_summary: 注语要点概括（一两句）。
- agreement_status: consensus|divergent|unique|unassessed。
- divergence_note / divergence_record: 与他注分歧时填写。
- 注释不得作为独立规则；必须依附 target_clause。

输出 JSON 字段：commentator, interpretation_type, interpretation_summary, agreement_status, divergence_note, annotation_flags。
