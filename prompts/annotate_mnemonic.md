# annotate_mnemonic · 医话/歌诀体标注器

输入是一段已被路由为 mnemonic_misc 的原文 span。

- sub_genre: verse（韵文歌诀）| note（医话笔记）。
- verse 时填 verse_fields: {verse_function: 方剂组成记忆|药性记忆|脉象记忆|治法记忆|穴位记忆|其他, target_type: formula|herb|pulse|other, target_name?: 如 麻黄汤, mentioned_herbs?: [歌诀中出现的药名]}。
- note 时填 note_fields: {note_type: 临证心得|读书札记|医林掌故|见闻杂记|warning_anecdote, summary}。
- 歌诀只作教学助记与交叉校验信号，**不得生成推理规则，不得作为证据绑定**。

输出 JSON 字段：sub_genre, verse_fields(或 note_fields), annotation_flags。
