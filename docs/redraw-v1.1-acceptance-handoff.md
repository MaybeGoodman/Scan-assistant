# Scan-assistant 图片重绘功能（V1.1 P0）独立验收交付说明

- **目标仓库**：`MaybeGoodman/Scan-assistant`
- **基线版本**：`main`（提交 `bed5749`，插件基线 `1.2.0`）
- **开发分支**：`feat/image-redraw-v1.1-p0`
- **需求依据**：《Scan-assistant 图片重绘功能开发需求（修订版 V1.1）》（严格按 P0 范围增量开发，未提前实现 P1 功能）
- **独立验收方**：ChatGPT

---

## 1. 基线差距核对与增量开发范围

开发前已对 `1.2.0` 基线执行离线包检查与全量回归（`310/310` 通过），识别出与 V1.1 P0 需求的主要差距并全部采用增量扩展方式补齐，未重写既有流程、未引入特定 AI 平台依赖：

| V1.1 P0 需求项 | 1.2.0 基线现状 | 本轮增量实现 | 兼容性说明 |
|---|---|---|---|
| 独立重绘与整卷提取并存（第 1 节） | 仅支持 `html`/`docx` 导出 | `pipeline.py` 新增 `--format images` 纯图交付（输出高清 PNG、结构化 SVG 及 `manifest.json`），`SKILL.md` 明确独立重绘边界 | 原 `html`/`docx`、Word 确认、`original`/`student` 模式不变 |
| 生成前事实描述扩展（第 3 节） | `validate_structure` 要求 `scene.structure == understanding` | `figure_drawing.py` 允许 `understanding` 携带 `fact_version`/`fact_changes`/`stem_context`/`evidence`/`design_allowances`/`uncertainties`/`verification_targets`，无需在 `scene.structure` 重复 | 旧版 `understanding` 与 `scene.structure` 完全兼容 |
| 图组 / 子图两级处理与混合路由（第 4.1 节） | 仅支持单级 `figure`，技术图与非技术图无法在同一图组分区路由 | `figure_workflow.py` 支持 `subfigures` 两级处理：每分区独立路由、独立复核、独立重试（每分区最多 2 次，已通过分区不重生成）；技术类子图强制结构化 `scene`，非技术类（`illustration` 或 `allow_generative:true` 的教学照片）可接入 `generated_png` 或降级为结构化/占位；全结构化合成 PNG+合规 SVG，混合图组合成正式 PNG 并保留子图 SVG | 旧版无 `subfigures` 的单图输入原样走既有路径 |
| 跨宿主能力降级（第 4.1 节） | 无显式工具不可用降级标记 | 支持 `drawing: {"tool_unavailable": true}`，优雅降级为占位或授权原图，不阻断正文、公式、表格及其他插图；不绑定任何在线生图 API | 全本地确定性渲染与校验，不依赖在线服务 |
| 实物器材与数据空间组件（第 4.2 节） | 仅有抽象电路符号与基础实验器材 | `figure_components.py`（模板版本 `1.3.0`）新增 `phys_meter`（无 `ranges` 时不编造量程）、`phys_knife_switch`（底座不横跨端子）、`phys_rheostat`、`phys_rotary_rheostat`、`phys_lamp_holder`、`phys_battery`、`phys_resistor`、`binding_post`、`clinical_thermometer`（35–42 ℃，0.1 ℃ 分度，不印答案）；增强 `alcohol_lamp`、`iron_stand`、`axes` 数据空间与 `data_curve` | 既有 18 类组件与 0.6.0/0.7.0/1.1.0 场景 100% 兼容 |
| 三项专项机器校验（第 4.3 节） | 仅校验整机 ID 对 `connections` 与简单单调曲线 | 新增 `validate_terminal_connections`（锚点几何校验，拦截接错邻端/悬空虚接/额外跨接/误触无关端子，区分同端共接与跨线无连接）、`validate_data_space`（关键数据点、平台重合段、实际液柱/指针读数）、`validate_state_checks`（相对位置与最小间隙、气泡单调半径） | 未声明新校验字段的旧场景保持原行为 |
| 依赖分级回退与手写回退边界（第 5.1 节） | 仅整图级回退 | 支持 `group_dependency: "strong"` / `strong_dependency: true` 整组回退、`dependency_group` 同组联动回退、独立子图局部占位/原图回退；新增 `--disallow-handwriting-fallback`，当源区含手写且未明确例外授权时，回退改用占位而非原图；关键不确定不消耗生成次数 | 默认 `placeholder` 与选项 D `original` 兼容 |
| 交付后局部返修与事实纠正（第 5.2 节） | 仅支持单次运行内 `retry`，不支持交付后局部修图与事实纠正 | 新增 `figure_workflow.prepare_repair` 与 `pipeline.py repair`：只重画目标 `figure_id[:subfigure_id]`，新任务版本重新获得 2 次预算；未修改分区直接复用不重生成，并用 `verify_unchanged_regions` 做像素级 100% 一致校验；事实纠正须提供 `reason`/`evidence` 并递增 `fact_version` | 不覆盖前次交付版本，完整保留 `parent_run_id` 与版本链 |
| 打印可读性检查（第 5.3 节） | 仅检查 PNG 像素与黑白 | 新增 `check_print_readability`（按 80 mm 单图 / 150 mm 多子图等效宽度检查最小标注字高与 `check_label_overlaps` 标注防重叠） | 仅作辅助检查，不替代真实视觉核验 |

---

## 2. 修改与新增文件清单

### 运行时脚本与技能规则
- `plugins/image-print-extractor/skills/image-print-extractor/scripts/figure_components.py`
- `plugins/image-print-extractor/skills/image-print-extractor/scripts/figure_drawing.py`
- `plugins/image-print-extractor/skills/image-print-extractor/scripts/figure_workflow.py`
- `plugins/image-print-extractor/skills/image-print-extractor/scripts/pipeline.py`
- `plugins/image-print-extractor/skills/image-print-extractor/scripts/export_page.py`
- `plugins/image-print-extractor/skills/image-print-extractor/SKILL.md`
- `plugins/image-print-extractor/skills/image-print-extractor/references/figure-redraw.md`

### 测试夹具、自动化回归与验收样例
- `tests/fixtures/redraw_v1_1/manifest.json`（R01–R12 回归夹具台账，明确标注真实扫描素材状态）
- `tests/test_redraw_v1_1.py`（10 组 V1.1 P0 专项正负例回归测试）
- `samples/v1_1_redraw/build_acceptance_samples.py`（可复现验收样例生成脚本）
- `samples/v1_1_redraw/out/`（生成的 PNG/SVG、局部返修前后对照、混合 Word 样例与 `acceptance_summary.json`）
- `docs/redraw-v1.1-acceptance-handoff.md`（本验收交付文档）

---

## 3. 实际测试与复现命令

在仓库根目录执行以下命令即可完整复现全部验证：

```bash
python3 -m pip install -r requirements-dev.txt
python3 scripts/validate.py
python3 -m unittest discover -s tests -v
python3 -X utf8 samples/v1_1_redraw/build_acceptance_samples.py
```

### 实测结果明细（分类独立报告）

| 验证类别 | 执行情况 | 实测结果 |
|---|---|---|
| 离线包与清单检查（`scripts/validate.py`） | 已执行 | **通过**（`Package checks passed`） |
| 既有功能全量回归（原有测试文件） | 已执行 | **310 / 310 通过**（0 失败，0 错误） |
| V1.1 P0 专项自动化回归（`tests/test_redraw_v1_1.py`） | 已执行 | **10 / 10 通过**（覆盖旧版兼容、混合图组与技术图守卫、R04 端子正负例、R05 体温计液柱读数偏差、R06 沸腾气泡与平台重合、R03 间隙校验与 R08 标签防重叠、R10 旋钮变阻器、R12 局部返修像素一致与事实版本递增、强依赖/独立/手写回退、无生图工具降级、纯图交付与混合 Word 导出） |
| 重绘图 PNG 人工视觉自查 | 已执行 | 已逐图检查 `R04`/`R05`/`R06`/`R10` 生成 PNG，并据此修正了体温计左端球部实心填充与指针表 `A`/`V` 字母避让 |
| R01–R12 真实扫描原图对照验收 | **未执行（缺真实原图素材）** | 本次开发会话未附带 R01–R12 真实扫描题图，已在 `tests/fixtures/redraw_v1_1/manifest.json` 全部标为 `pending_real_source_material`（待补素材／待验收），**不宣称真实原图对照已通过** |
| Word 页面实际排版渲染验收 | **未完成页面截图渲染** | 当前 Linux 开发环境未安装 LibreOffice / MS Word，已用 `python-docx` 校验内嵌图片数量、原位顺序、占位文本与 `draft` 草稿页眉标记；需在 Word / LibreOffice 中打开 `.docx` 完成最终打印排版核验 |

---

## 4. 供 ChatGPT 独立验收的成品对照

所有成品均位于 `samples/v1_1_redraw/out/`，详细哈希与可读性指标见 `samples/v1_1_redraw/out/acceptance_summary.json`：

### 4.1 纯重绘图片与等效打印可读性（80 mm 单图 / 150 mm 多子图）

| 样例 | 产物路径 | PNG 尺寸（300 dpi） | 等效打印检查 | 说明 |
|---|---|---|---|---|
| R04 实物电路 | `samples/v1_1_redraw/out/R04_physical_circuit.png`<br>`samples/v1_1_redraw/out/R04_physical_circuit.svg` | `1314×1227` | 80 mm 宽最小标注 `1.83 mm`，0 重叠，通过 | 串联 2 节干电池（`+ -` 可追踪）、双断开闸刀开关、指针式 A/V 表（不编造量程）、小灯座，通过逐端子锚点几何校验 |
| R05 体温计 | `samples/v1_1_redraw/out/R05_clinical_thermometer.png`<br>`samples/v1_1_redraw/out/R05_clinical_thermometer.svg` | `1074×180` | 80 mm 宽最小标注 `2.01 mm`，0 重叠，通过 | 35–42 ℃ 量程，0.1 ℃ 小格，0.5 ℃ 中格，1 ℃ 主格，数据空间液柱精确止于 `37.8 ℃`，图内不印答案 |
| R06 沸腾实验三子图组 | `samples/v1_1_redraw/out/R06_boiling_group.png`<br>`samples/v1_1_redraw/out/R06_boiling_group.svg` | 组合高清 PNG + 合规组合 SVG | 三子图（甲/乙/丙）清晰无重叠，通过 | 甲：铁架台+夹具+铁圈+石棉网+带液面/内外焰/底座酒精灯+烧杯+温度计；乙：气泡 `a` 上升变大、`b` 上升变小；丙：曲线 I `(0,92)->(6,98)` 与 II `(0,90)->(8,98)` 后 `[8,10]` 平台重合 |
| R10 旋钮式变阻器 | `samples/v1_1_redraw/out/R10_rotary_rheostat.png`<br>`samples/v1_1_redraw/out/R10_rotary_rheostat.svg` | `672×429` | 80 mm 宽最小标注 `3.93 mm`，0 重叠，通过 | `A`/`C` 接电阻丝两端、`B` 接滑片轴心，三条引线准确指向“旋钮”“滑片”“电阻丝” |

### 4.2 局部返修前后对照（R12）

- **返修前**：`samples/v1_1_redraw/out/R12_repair_before.png`
- **返修后**：`samples/v1_1_redraw/out/R12_repair_after.png`
- **返修动作**：仅针对 `f_r06:bing` 发起外观局部返修（`task_version: 2`），微调丙图标签 `II` 位置；`jia` 与 `yi` 两个未修改分区直接复用原渲染产物，未重新生成，并在重新合成后通过 `verify_unchanged_regions` 像素级 100% 一致校验（`unchanged_regions_verified: ["jia", "yi"]`）。

### 4.3 混合 Word 样例（R12）

- **文件路径**：`samples/v1_1_redraw/out/R12_mixed_exam_sample.docx`
- **包含场景**：
  1. 第 1 题：R04 实物电路（结构化单图原位嵌入）
  2. 第 2 题：R06 沸腾实验（多子图合成图组原位嵌入）
  3. 第 3 题：R05 体温计（数据空间精确读数原位嵌入）
  4. 第 4 题：R11《天工开物》透火焙干（模拟宿主无图像生成工具 `tool_unavailable: true` 优雅降级为原位占位 `[第4题透火焙干：无法可靠重绘]`）
- **交付门禁验证**：因含 1 处失败占位（`failed_figures: ["f_r11"]`），导出自动保持 `delivery: "draft"`（`open_review_items: 1`），不会将未决回退项静默冒充为正式重绘成品。

---

## 5. 已知不足与非本轮事项

1. **R01–R12 真实扫描原图待补齐**：本次交付的样例使用合成占位原图验证程序机制与渲染可读性。待用户或验收方补齐 R01–R12 真实扫描题图及放大确认的原图真值（尤其是 R02 四冲程原图、R04 真实印刷接线、R05 放大确认的真实液柱终点、R07 印刷/手写区分真值、R10 图1/图2原图）后，需逐案复跑并由 ChatGPT 完成真实原图对照验收。
2. **Word 实际打印预览未截图**：当前环境无 LibreOffice/Word 渲染器，未能附带 `.docx` 页面渲染截图，需在办公软件中打开 `R12_mixed_exam_sample.docx` 核验实际分页与缩放效果。
3. **生成式插画实测依赖运行宿主**：本插件保持跨宿主中立，不绑定特定生图 API；`generated_png` 接入校验与 `tool_unavailable` 降级已通过自动化测试，但 R01、R11 的真实生图视觉表现需在具备图像生成能力的宿主中实测。
4. **明确留待 P1 的事项（本轮未提前实现）**：浅灰/排线填充扩展、穷举式多视角器材库、自动化印刷/手写视觉分割、跨学科通用科学模拟器。
