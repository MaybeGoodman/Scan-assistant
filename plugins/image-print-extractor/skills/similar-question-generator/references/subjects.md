# 八个模块的范围与复核清单

机器可读版本在 `<scripts>/subjects.py`，提交候选时 `review.checklist` 必须包含对应模块的全部键，并且全部为 `true`。

| 模块 | 学段·学科 | 默认教材 | 至少一项确定性检查 | 典型结构 |
|---|---|---|---|---|
| M01 | 初中·数学 | 华东师大版，初一至初三 | arith、substitute、roots 之一 | 方程或函数、几何图、多小问应用题 |
| M02 | 初中·物理 | 沪科版 | units、arith、substitute 之一 | 力热基础计算、电路或光路、实验题 |
| M03 | 初中·化学 | 沪教版 | balance、arith 之一 | 基础方程式、质量计算、装置与操作题 |
| M04 | 初中·英语 | 仁爱版，初一至初三 | choice、evidence 之一（开放写作用 rubric） | 语法选择、完形或阅读共享语篇、情境写作 |
| M05 | 高中·数学 | 人教版 A 版 | arith、substitute、roots 之一 | 函数或数列、三角、解析或立体几何、概率统计综合 |
| M06 | 高中·物理 | 鲁科版 | units、arith、substitute 之一 | 多阶段计算、受力或运动图、电磁和实验数据题 |
| M07 | 高中·化学 | 苏教版 | balance、arith 之一 | 离子与氧化还原方程式、实验装置、电化学或综合推断 |
| M08 | 高中·英语 | 北师大版 | choice、evidence 之一（开放写作用 rubric） | 完形、推断型阅读、应用文或相同任务类型的写作 |

高中覆盖相应教材的必修与选择性必修范围，具体课时进度由本次任务输入约束。具体版次、册次与单元映射**本插件未内置**：无法确认某知识点属于哪一册时，如实说明“教材单元未知”，不要编造章节。原题识别不受教材限制；教材只约束生成新题的知识范围。

## 复核清单

**M01 初中数学**

- `solution_exists`：解存在，唯一性符合设问；无解或多解要说明。
- `domain_parameters`：定义域、参数取值与题设一致。
- `geometry_conditions`：几何条件自洽，图形可画，证明链完整。
- `steps_controlled`：计算量和推理步数与原题相当。
- `junior_scope`：只用初中方法即可完成。

**M02 初中物理**

- `model_kept`：物理模型和规律与原题一致。
- `units_checked`：单位、数量级核算通过。
- `direction_range`：方向、量程、读数合理。
- `figure_consistent`：电路连接、光路或受力与题干一致。
- `junior_method`：只用初中方法即可完成。

**M03 初中化学**

- `principle_kept`：反应原理、体系和计量模型与原题一致。
- `formula_mass`：式量计算正确。
- `conservation`：元素守恒、质量守恒成立，方程式已配平。
- `conditions_apparatus`：反应条件、试剂和装置合理。
- `junior_scope`：不依赖高中知识。

**M04 初中英语**

- `target_language`：目标词汇、语法和语言任务与原题一致。
- `length_vocabulary`：句长、篇幅和词汇在初中范围内。
- `unique_answer`：客观题选项互斥，答案唯一。
- `evidence_located`：阅读题答案能在语篇中定位。
- `task_executable`：写作任务要求清楚、可以完成。

**M05 高中数学**

- `core_idea`：核心数学思想与小问梯度与原题一致。
- `domain_parameters`：定义域、参数区间正确。
- `boundary_cases`：边界与退化情形已检查。
- `solution_set`：解集、最值或图像结论经独立重算。
- `geometry_proof`：几何关系或证明经验证；题目不涉及几何时写 `true`，并在 notes 中说明。

**M06 高中物理**

- `model_kept`：受力、运动、能量或电磁模型与原题一致。
- `units_signs`：单位、符号和方向核算通过。
- `initial_boundary`：初始条件和边界条件可以实现。
- `chained_quantities`：小问之间传递的物理量正确。
- `figure_consistent`：图表条件与题干一致。

**M07 高中化学**

- `system_kept`：反应体系和综合层级与原题一致。
- `conservation`：元素守恒、电荷守恒、电子守恒成立。
- `equilibrium_electrochem`：平衡、电化学或离子反应判断正确。
- `reagents_apparatus`：试剂和装置合理。
- `inference_chain`：推断链唯一，可以完成。

**M08 高中英语**

- `language_natural`：语言自然地道，句法复杂度与原题相当。
- `evidence_sentences`：答案有证据句支撑，推断层级与原题一致。
- `no_ambiguity`：选项无歧义，答案唯一。
- `discourse_ability`：篇章能力目标与原题一致。
- `task_standard`：开放题可以按任务标准核验。

高中物理以计算、实验、综合分析为重点。题型配比不作强制要求，由用户的本次请求决定。
