# annotate_pulse · 脉学体标注器

输入是一段已被路由为 pulse_text 的原文 span。抽取脉象本体：

- pulse_name: 脉名（浮脉）。
- definition: 指感定义原文（举之有余，按之不足）。
- dimensions: [{dimension: 深浅|速度|力度|形态|紧张度|流利度|节律|部位, polarity: 该维取值（浮/沉、迟/数等）}]，至少一项。
- differential_pairs: [{vs_pulse, distinction}]（浮与芤相类，何以别之）。
- syndrome_associations: [{association, strength: weak_default|context_dependent}]——**所有脉证关联默认 weak_default**，禁止单脉定证硬规则。
- feature_decomposition_rules: [{compound_surface: 脉浮紧, components: [浮, 紧], decomposable: true}]。

输出 JSON 字段：pulse_name, definition, dimensions, differential_pairs, syndrome_associations, feature_decomposition_rules, annotation_flags。
