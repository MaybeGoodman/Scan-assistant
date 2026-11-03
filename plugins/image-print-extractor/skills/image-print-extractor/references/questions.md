# 题目结构、输出模式与交付状态（V1.0）

本规则在原有 `blocks` 之上增加可选元数据，不改变 0.8.1 已复核 JSON 的含义：没有这些字段的旧文档仍按原样导出，交付状态由内容本身判定。

## 何时需要

- 用户要“学生版”“去掉答案”“做成练习”，或要基于原题生成同类题时，必须给块标注 `id` 和 `role`，并建立 `questions` 索引。
- 只提取原题、只转 Word 时可以不标注；但标注后同一份 JSON 可以直接复用于学生版和出题，不必重新识别。
- 语义角色由宿主看图和读题判断，脚本只校验引用和执行投影，不按“答案”“解析”等关键词删除内容。

## 块与角色

| role | 含义 | 学生版 |
|---|---|---|
| title、stem、material、option、subquestion、answer_space、figure、instruction、source、other | 题目内容 | 保留 |
| answer、analysis、solution、filled_answer、answer_mark、scoring | 印刷答案、解析、解答、已填答案、正确项标记、评分标准 | 移除（表格单元格清空但保留格子） |
| uncertain | 无法判清是否属于答案材料 | 保留，并进入待复核 |

`role` 可以写在块、段内 run 或表格单元格上。例如题干末尾印着“（答案：B）”时，把它拆成单独的 run 并标 `answer`。学生版还会清空图片替代文字，以免描述中带出答案。

未标注 role 的段落按题目内容保留。学生版中，以“答案／解析／故选”等标签开头而未标注的段落会被列为待复核项，**不会被自动删除**。

## 题目索引

```json
{
  "blocks": [
    {"type": "text", "id": "p1-3", "role": "stem", "runs": [...]},
    {"type": "image", "id": "p1-4", "role": "figure", "figure_id": "f1", "path": "..."},
    {"type": "text", "id": "p1-5", "role": "subquestion", "text": "（1）……"},
    {"type": "text", "id": "p1-6", "role": "subquestion", "text": "（2）……"},
    {"type": "text", "id": "p1-9", "role": "answer", "text": "【答案】……"}
  ],
  "materials": [{"material_id": "m1", "blocks": ["p1-1"]}],
  "questions": [{
    "question_id": "q18", "number": "18", "module": "M05", "question_type": "comprehensive",
    "blocks": ["p1-3", "p1-4", "p1-9"], "materials": ["m1"],
    "subquestions": [
      {"subquestion_id": "q18-1", "number": "(1)", "blocks": ["p1-5"]},
      {"subquestion_id": "q18-2", "number": "(2)", "blocks": ["p1-6"], "depends_on": ["q18-1"]}
    ],
    "source_spans": [{"attachment": "第2页.png", "page": 2, "bbox": [80, 300, 1150, 900]}],
    "review_status": "confirmed",
    "completeness": {"complete": true, "missing": []}
  }]
}
```

- 每个引用列表须按正文阅读顺序排列。一个块只能属于一道题；共享语篇或数据放进 `materials`，由各题引用。
- `depends_on` 只能指向排在前面的小问。
- 跨页、跨批的大题共用同一个 `question_id`，在 `source_spans` 中逐段登记原页和区域。指定页范围切断大题时，写 `"completeness": {"complete": false, "missing": ["第3页的第（3）问"]}`，并提示用户补页。
- `module` 取 M01–M08，见 similar-question-generator 技能。原题识别不受教材限制，`module` 只影响生成。
- `review_status` 只有在回看原图、确认题目边界、小问、材料与图表归属后才写 `confirmed`。

## 输出模式

流水线和导出器都支持 `--output-mode original|student`，默认 `original`：

- **original**：原题还原，印刷答案与解析按原位置保留。这与 0.8.1 的行为一致。
- **student**：从同一份结构中投影，移除答案角色内容，保留题干、条件、选项、答题空间和有效图表。导出后自动审计 Word 包，覆盖正文、表格、公式、页眉页脚、批注、修订、隐藏文字、自定义 XML、嵌入对象、图片替代文字和文档属性，发现答案片段即删除该文件并报错。内部复核报告只记录被移除项的位置，不记录答案原文。

## 交付状态

导出结果和流水线摘要都给出 `delivery`。`status` 和 `next_action` 的含义不变，`completed` 仍只表示执行结束。

- **final**：请求范围内没有未处理的复核项。
- **draft**：存在任一待复核项。Word 每页页眉印“【待复核草稿】……”，HTML 和 Markdown 首行写同样的提示，正文内容不变。向用户交付时必须说明这是草稿。

待复核项包括：
- 推断补写的 `〔〕`、无法辨认的 `XXX`、不可识别或转换失败的表达式。
- 化学式未能直接呈现（已保留源码）、重绘失败的插图占位。
- 未确认的题目结构、不完整的题目、角色不明的内容、疑似未标注的答案，以及主体筛选中不确定而保留的元素。

复核：逐项回看原图，核对报告 `review_items` 中的每一项。确认无误或接受现状后，写入：

```json
{"resolutions": [{"key": "<review_items 中的 key>", "resolution": "confirmed", "by": "host", "note": "回看原图：残笔为“6”"}]}
```

`resolution` 取 `confirmed`（已核对原图确认）或 `accepted`（用户接受该缺项）；`by` 为 `host` 或 `user`。然后运行：

```text
python -X utf8 <skill-dir>/scripts/pipeline.py finalize --state <state> --resolutions <文件> --output <新的 .docx 或目录>
```

`key` 绑定位置和内容哈希。内容被修改后，原有确认会失效，`finalize` 拒绝沿用过期确认。待复核的关键条件同时会阻止该题进入同类题生成。
