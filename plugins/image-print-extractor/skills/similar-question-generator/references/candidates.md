# 候选文件格式

每个候选是一道完整新题，单独存成一个 UTF-8 JSON 文件，放在源 JSON 所在目录内，配图路径相对该目录。`submit` 会冻结候选 JSON 和每张配图（PNG，以及有的 SVG）的副本并记录哈希；交付只使用这些冻结副本，并重新核对冻结副本和原文件的哈希：提交后原图被改动或删除，交付会被拒绝，需修正后重新提交该变式。

```json
{
  "question_id": "q18",
  "slot": 1,
  "variant": {
    "blocks": [
      {"type": "text", "id": "stem1", "role": "stem", "runs": [{"type": "text", "text": "如图，在"}, {"type": "math", "latex": "\\triangle ABC"}, {"type": "text", "text": "中……"}]},
      {"type": "image", "id": "fig", "role": "figure", "path": "variant-figs/v1.png", "alt": ""},
      {"type": "text", "id": "s1", "role": "subquestion", "text": "（1）求证：……；"},
      {"type": "text", "id": "s2", "role": "subquestion", "text": "（2）求……；"},
      {"type": "text", "id": "s3", "role": "subquestion", "text": "（3）求……。"}
    ],
    "stem": ["stem1", "fig"],
    "materials": [],
    "subquestions": [
      {"number": "(1)", "blocks": ["s1"], "depends_on": []},
      {"number": "(2)", "blocks": ["s2"], "depends_on": []},
      {"number": "(3)", "blocks": ["s3"], "depends_on": ["(2)"]}
    ]
  },
  "design": {
    "knowledge_points": ["等腰三角形三线合一", "勾股定理"],
    "method": "全等证明→勾股定理→等积法",
    "question_type": "几何综合（证明＋计算）",
    "difficulty": "same",
    "difficulty_evidence": "三小问，证明一步全等，计算两步，与原题相同",
    "difference_from_source": "证明目标由角平分改为垂直，数据改为 5-12-13",
    "difference_from_siblings": "直接给腰和底"
  },
  "internal": {
    "answers": [{"item": "(1)", "answer": "……"}, {"item": "(2)", "answer": "AD=12"}, {"item": "(3)", "answer": "DE=60/13"}],
    "solution": "BD=5，AD=√(13²−5²)=12；13·DE=5·12，DE=60/13。",
    "checks": [
      {"kind": "arith", "item": "(2)", "expr": "sqrt(13**2-5**2)", "expect": "12"},
      {"kind": "semantic", "item": "(2)", "independent_answer": "AD=12", "method": "独立重算"}
    ]
  },
  "review": {
    "checklist": {"solution_exists": true, "...": true},
    "notes": ["逐问独立重算并核对清单"],
    "figures": [{"id": "fig", "sha256": "<实际查看的 PNG 的 sha256>", "reviewed_by": "host_vision", "status": "pass",
                 "checks": {"consistent_with_text": true, "labels_complete": true, "no_answer_content": true, "print_legible": true},
                 "notes": ["看图核对：……"]}]
  }
}
```

要点：

- 题面块只放学生可见内容，不得出现 `answer` 等答案角色；数学、化学用有类型的 runs（规则同提取技能）。
- `subquestions` 的 `number` 与原题逐一对应，`depends_on` 写所依赖小问的编号。
- 每个块只能属于一处：题干（`stem`）、共享材料（`materials`）或某一个小问。不同小问不得引用同一个块，小问也不得引用题干块；每个小问至少有一个带文字的题面块。复用别处的块冒充某一小问会被判为失败。
- 题面中不得出现 `〔〕`、`XXX`、`status: unresolved` 的表达式、`role: uncertain` 或插图占位。新题没有“原文”可推断，出现这些即判为失败，不计入合格数，改好后作为新候选重新提交。
- 每张配图都要在 `review.figures` 中有一条视觉复核：`id` 对应图块，`sha256`（有 SVG 时另加 `svg_sha256`）是实际查看的文件哈希，`reviewed_by` 为 `host_vision`，`status` 为 `pass`，四项 `checks` 如实逐项核对后才能为 `true`。哈希不符、缺项或任一项为 `false`，候选不通过。不得照抄示例或一律填 true。
- `internal.answers` 每个小问一条，没有小问时 `item` 写 `"all"`。
- `design.open_task: true` 表示开放写作或开放实验题，此时必须提供 `rubric` 检查。

## 检查类型

每条检查都带 `kind` 和 `item`（所验证的小问编号，或 `"all"`）。

| kind | 字段 | 判定 |
|---|---|---|
| arith | expr, expect, tolerance | 表达式求值等于期望值（默认精确分数比较） |
| substitute | equation（恰好一个 `=`）, vars | 代入后左右两边相等 |
| roots | expr, var, claimed, interval | 所列的根都满足方程。多项式用精确有理系数和 Sturm 序列判定闭区间内的全部不同实根（含偶重根和端点根），有遗漏即失败；非多项式（含除以变量、根号、三角函数等）无法证明没有漏根，结果为“不确定”，候选进入 `needs_review`。interval 端点需为有理数 |
| units | expr, units, expect | 量纲分析结果等于期望单位（支持 kg、m/s^2、Ohm/Ω、V、A、J、W、Pa 等） |
| balance | equation，如 `Cu + 2Ag^+ = Cu^2+ + 2Ag` | 元素守恒、电荷守恒（离子电荷写 `^`，电子写 `e-`） |
| choice | options, answer, multi | 答案在选项内；单选恰好一个答案；选项内容不重复 |
| evidence | quote | 证据句确实出现在学生题面中 |
| semantic | independent_answer, method, uncertain | 独立求解结果与内部答案一致；`uncertain: true` 时候选进入待复核 |
| rubric | criteria（至少 3 条）, satisfied | 开放题按标准核验 |

表达式只支持加减乘除、乘方和 sqrt、sin、cos、tan、log、ln、exp、abs，以及 pi、e，不执行任意代码。

此外，脚本还会检查以下各项，任一不满足即判为失败：
- 小问数量、顺序和依赖与原题一致；原题有共享材料或配图时，新题也有。
- 答案没有出现在题面中。
- 与原题、与已通过的同组题的相似度在阈值以内（原题 0.98，同组题 0.95）。
- 难度与请求一致，设计字段填写完整，模块清单全部为 `true`。
