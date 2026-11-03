# Scan-assistant V1.0 候选交付报告（开发自测）

| 项目 | 内容 |
|---|---|
| 依据 | 《Scan-assistant V1.0 功能需求与开发验收说明书》（2026-11-03），R01–R12 |
| 基线 | `main` @ `5957490f319348efdb52f3aefd17d2c7d33f424b`，插件 0.8.1；接手时工作区干净，`validate.py` 通过，回归 205/205 通过 |
| 候选分支 | `feat/1.0.0-v1-candidate`。候选 SHA 以 PR 页面和交接消息中给出的提交为准；本报告随该提交一同提交 |
| 版本 | 三份插件清单为 `1.0.0`，Claude 市场目录描述同步更新；Codex 市场目录无版本或描述字段，无需改动 |
| 开发与自测 | Claude（Opus 5.5，云端 Linux 工作区）。本报告只记录开发侧结果；ChatGPT 独立验收的结果不在本报告中 |
| 状态 | 候选版本，未合并、未发布 |

## 1. 修改范围

新增脚本，均位于 `plugins/image-print-extractor/skills/image-print-extractor/scripts/`，两个技能共用：

| 文件 | 作用 |
|---|---|
| `questions.py` | 题目、小问、材料索引校验；语义角色；学生版投影；待复核项收集与交付结论；答案片段比对 |
| `chemistry_word.py` | 化学 LaTeX 子集解析：简单式输出 Word 富文本上下标，复杂式输出专用 OMML |
| `docx_audit.py` | 学生版 Word 包泄漏审计；Word 与 JSON（聊天）内容一致性检查 |
| `subjects.py` | M01–M08 模块、默认教材、复核清单 |
| `variant_checks.py` | 无第三方依赖的确定性校验：arith、substitute、roots、units、balance、choice、evidence、semantic、rubric |
| `variants.py` | 同类题台账：`init`、`submit`、`status`、`deliver` |

修改的已有脚本，均为增量修改：

| 文件 | 修改 |
|---|---|
| `export_docx.py` | 新增 `output_mode`、`chemistry_format`；草稿页眉；报告增加 `delivery`、`review_items`；学生模式保存后审计。旧调用参数不变 |
| `export_page.py` | `export()` 签名兼容；新增 `export_result()` 返回交付信息；学生模式；草稿首行提示 |
| `pipeline.py` | 新增 `--output-mode`、`--chemistry-format`；摘要增加 `delivery` 等字段；新增 `finalize` 子命令；主体筛选中不确定的项计入复核 |
| `confirmation.py` | 新增 `generate` 一项；未询问该项时输出字段与 0.8.1 完全相同 |
| `figure_workflow.py` | 失败占位块保留原块的 `id`、`role`，并增加 `figure_placeholder` |

技能与文档：
- 新技能 `skills/similar-question-generator/`：`SKILL.md`、`references/subjects.md`、`references/candidates.md`、`agents/openai.yaml`、图标。
- 提取技能：更新 `SKILL.md`，新增 `references/questions.md`，修订 `formulas.md`、`pdf-word.md`、`rich-output.md`。
- `docs/REQUIREMENTS.md` 新增第 71–78 节；`docs/acceptance.md` 新增第 39–56 项；更新 `CHANGELOG.md`、`README.md`。

测试：
- 新增 `tests/test_v1_delivery.py`（21 项）、`tests/test_v1_variants.py`（8 项）。
- 迁移 3 个测试文件中 4 处断言“Word 中化学为源码文本”的用例，改为显式传 `chemistry_format='source'`，以证明兼容路径仍然可用。

其他：
- `scripts/validate.py` 增加检查：技能引用的同插件脚本目录必须存在。
- `.gitignore` 忽略样本工作目录。
- 新增 `samples/v1/`：原创内容、合成页面渲染、构建脚本、开发侧插图复核结论和全部实际成品。

## 2. 需求对应表

| 需求 | 实现 | 自动化测试 | 样本证据 | 开发侧结论 |
|---|---|---|---|---|
| R01 八模块 | `subjects.py`；两个技能的规则；`MODULE_KINDS` | `SubjectCheckTests.test_eight_modules_have_checklists` | M01–M08 各一道综合原题、三道变式 | 开发自测通过；真实教材样本未测 |
| R02 忠实提取 | 0.8.1 提取链路不变；新增题目索引、来源区域、跨页同一身份 | 原有 205 项；`QuestionIndexTests` | 8 份合成扫描页→`original.docx`（水印、页眉、手写已过滤，印刷答案保留） | 自测通过；真实视觉识别由宿主承担，未在真实扫描件上测 |
| R03 可编辑 Word 与化学直接显示 | `chemistry_word.py`、`export_docx.py` | `ChemistryWordTests`（正文、选项、表格、失败草稿、兼容路径） | M03、M07 的 Word 及 `render/` 页面；编辑后重开、LibreOffice 往返均保留 OMML 与上下标 | LibreOffice 渲染通过；**Microsoft Word 未运行** |
| R04 黑白重绘 | 复用 0.8.1 流程；变式配图用结构化绘图并校验黑白 | 原有图片测试；`verify` 要求原题有图时变式也有图 | M01 几何、M02 电路：开发侧逐张对照复核（`samples/v1/reviews/`）；变式按新数据重画 | 自测通过；F02 失败回退沿用 0.8.1 测试，未做新样本 |
| R05 原题版／学生版 | `questions.project()`、`--output-mode` | `StudentProjectionTests`、`test_student_word_has_no_answers_and_matches_chat` | 每模块 `original.docx` 与 `original-student.docx` | 自测通过 |
| R06 完整大题＋默认三道 | `variants.init/verify`：小问数、编号、依赖、材料、图 | `test_structure_isolation_and_checklist_failures` | 8 模块 × 3 道 = 24 道，全部 3 问、依赖一致 | 自测通过 |
| R07 同类与难度 | `design` 字段、难度一致性、相似度阈值、`--learner`、`--scope-override` | 同上 | M05 降低、提高难度各一道；开发中有 3 次近重复被真实拦截（见 §4.3） | 自测通过；难度高低的判断依据由宿主填写，脚本只校验一致性 |
| R08 提取后询问一次 | `SKILL.md` 规则；`confirmation.py --ask generate` | `GenerateConfirmationTests` | 无（需真实宿主交互） | 解析器通过；**交互流程未在宿主中运行** |
| R09 逐题验证与重试 | `verify`：独立求解比对、模块确定性检查、清单；有限重试；部分交付 | `test_retry_budget_partial_delivery_and_duplicate`、`test_injected_errors_by_subject`、`test_tampered_candidate...` | M03 注入（未配平、答案不符、雷同）→2/3 部分交付；M02 单位、M05 漏根、M04 双答案→`blocked` | 自测通过 |
| R10 聊天＋Word，学生版无答案 | `deliver`：同一份 JSON 生成两种格式；一致性检查；包审计；答案只在 `internal/` | `test_three_passing_variants_deliver_final_student_package`、`test_delivery_requires_word_confirmation_and_separate_folder` | 每模块 `variants/student.docx` 与 `student-chat.md`；`summary.json` 中审计结果均为 `ok` | 自测通过 |
| R11 推断复核与草稿 | `review_items`、`delivery_status`、草稿页眉、`finalize`、生成门槛 | `DeliveryGateTests`、`PipelineFinalizeTests`、`test_gate_refuses...` | M06：遮挡→`〔6〕`→草稿→生成被拒→复核→`original-final.docx`→生成 | 自测通过 |
| R12 ChatGPT 与 Codex 双端 | 两个技能同一插件；Codex 与 Claude 清单；编号文本确认入口沿用 | `validate.py` | 无 | **ChatGPT、Codex 均未运行**，见 §3.3 |

## 3. 测试结果

四类结果分开记录，任一类通过都不代表其他类已通过。

### 3.1 离线回归（已运行）

- 环境：Linux 6.18，Python 3.13.18；python-docx 1.2.0、lxml 6.1.3、Pillow 12.3.0、latex2mathml 3.81.1、pypdfium2；按 `requirements-dev.txt` 安装依赖。
- `python scripts/validate.py`：`Package checks passed`，退出码 0。
- `python -m unittest discover -s tests -v`：234 项全部通过，退出码 0。其中原有 205 项、新增 29 项。
- 原有测试中有 4 处断言“Word 中化学为源码文本”，已迁移为显式 `chemistry_format='source'`；其余原有测试未修改。
- CI（GitHub Actions：Ubuntu Python 3.10 与 Windows Python 3.12）：推送后的运行结果见 PR 页面。本报告不预先声称已通过。

### 3.2 开发侧端到端（Claude 云端工作区，已运行）

命令：`python -X utf8 samples/v1/build_samples.py stage1`，然后 `stage2`。汇总见 `samples/v1/out/summary.json`。

| 模块 | 原题版交付 | 生成结果（合格／请求） | 学生包 | 学生包审计 |
|---|---|---|---|---|
| M01 | final | 3/3 | final | ok |
| M02 | final | 3/3 | final | ok |
| M03 | final | 3/3 | final | ok |
| M04 | final | 3/3 | final | ok |
| M05 | final | 3/3 | final | ok |
| M06 | draft→复核→final | 3/3（草稿状态下 `init` 被拒绝） | final | ok |
| M07 | final | 3/3 | final | ok |
| M08 | final | 3/3 | final | ok |

附加用例：

| 用例 | 结果 |
|---|---|
| G02 难度 | M05 降低难度 1/1、提高难度 1/1 |
| G04 注入 | M03 先后提交未配平、答案与独立求解不符、与同组雷同 → 2/3，`partial`，报告“第16题目标 3 道，验证通过 2 道，缺 1 道”；M02 单位错误、M05 漏根、M04 单选双答案 → 各 0/1，`blocked`，不生成学生文件 |

人工复核：
- **插图**：M01、M02 由开发侧逐张查看原图裁片与重绘 PNG 后填写复核（主体、连接、标注、直角标记、比例），结论为 `pass`。原图由同一场景渲染后加噪，属自测性质。
- **题目正确性**：开发侧逐题手工复算了全部 26 道新题（24 道基础变式和 2 道难度题），数学、物理、化学答案与内部答案一致；英语题核对了证据句和选项唯一性。这仍是作者自查，学科正确性需验收侧独立重解。

### 3.3 ChatGPT 与 Codex 实测（未运行）

| 用例 | ChatGPT | Codex | 原因 |
|---|---|---|---|
| P01 / P02 端到端 | NOT_RUN | NOT_RUN | 开发环境没有这两个宿主，无法安装或调用插件，也无法从真实附件发起任务 |
| G03 四种交互路径 | NOT_RUN | NOT_RUN | 需要真实宿主对话；开发侧只测了回答解析 |
| A01–A04 真实视觉识别 | NOT_RUN | NOT_RUN | 没有真实教材或试卷扫描件；样本为合成页，转录由开发侧依据页面内容完成，不能代表宿主的视觉识别准确率 |
| X02 宿主受限场景 | NOT_RUN | NOT_RUN | 需要在宿主中构造“不能执行文件”“缺少依赖”等条件 |

ChatGPT 端的分发方式（插件或 Skill 上传）尚未在候选环境中验证。两个技能需要一起安装（生成技能使用提取技能的 `scripts/`）；只上传单个技能时，生成技能无法运行。

### 3.4 Word 编辑与打印检查（部分运行）

| 检查 | 结果 |
|---|---|
| LibreOffice 24.2 渲染 | 全部成品已渲染为 PDF 与 PNG（`samples/v1/out/*/render/`），开发侧逐页查看过 M01、M02、M03、M04、M05、M06、M07 的代表页 |
| 编辑后重开 | 用 python-docx 修改正文后保存再打开：OMML 数量、上下标格式、图片数量不变（M03、M07、M01、M05） |
| LibreOffice 往返 | 打开后另存为 docx：OMML 数量、上下标格式、图片数量不变 |
| Microsoft Word | **NOT_RUN**：环境中没有 Word。编辑公式和化学式、保存重开、打印预览、黑白打印，需由验收侧在真实 Word 中完成（W01–W03） |

本环境起初缺少 `libreoffice-math`，导致所有 OMML 在渲染中消失。用 0.8.1 基线导出的文件对照后，确认是环境缺件而非回归，安装后恢复正常。

## 4. 设计决策与偏离（D 项）

### 4.1 题目索引方案（D10）

- 采用向后兼容的附加字段：块 `id`、`role`，顶层 `questions`、`materials`、`review_resolutions`。字段含义见 `references/questions.md`。
- 没有这些字段的 0.8.1 文档导出不变。答案角色由宿主标注；脚本不按关键词删除内容，只把疑似答案列为待复核项。

### 4.2 化学 Word 表示（D03）

- 简单式用 Word 富文本上下标：教师可以像普通文字一样修改。
- 复杂式（反应条件、核素、化合价、分式）用专用 OMML，规则如下：
  - 每个字母为“普通文字”（`m:nor`），保证正体。
  - 条件用“长箭头＋上方／下方限”（`limUpp`/`limLow`）。
- 最初采用 `groupChr`（Word 中可伸缩的箭头），但 LibreOffice 不支持，渲染为“¿”，且字母显示为斜体。改用上述结构后，两种软件都能正确显示。代价是箭头不随条件文字伸缩。
- 不支持的写法保留源码并进入草稿；0.8.1 源码行为可显式选用。

### 4.3 同类性与相似度阈值（D05）

- 与原题相似度 ≥ 0.98 判为复刻，与同组已通过题 ≥ 0.95 判为近重复。阈值写在 `variants.py` 的 `SOURCE_REPLICA`、`SIBLING_DUPLICATE`，可调整。
- 开发中，M02、M03、M05 的变式最初只换了数字（相似度 0.97–0.98），被真实拦截。改写情境与条件呈现方式后通过，说明阈值能挡住只改数字的雷同题。
- 相似度只衡量文字层面的雷同，训练差别是否合理仍由宿主在 `design` 中说明，并经复核判断。

### 4.4 重试上限（D07）

默认每个位置最多 3 次，可用 `--max-attempts` 设为 1–10。

### 4.5 验证记录（D06）

每个候选保存为冻结副本并记录哈希，台账记录检查结果、失败原因和尝试次数；交付时重新核对哈希。“独立求解”由宿主在单独步骤中完成，脚本只比对结果是否一致，不能证明宿主确实独立求解。这一点需验收侧通过重解来核对。

### 4.6 状态（D08）

- 保留 `status`、`next_action` 的原有含义，新增 `delivery`。
- 部分交付（`partial`）与阻断（`blocked`）由生成台账给出；提取流水线只给出 `final` 或 `draft`。

### 4.7 宿主适配（D11）

- 确认继续兼容编号文本回答。
- 生成技能通过 `<skill-dir>/../image-print-extractor/scripts` 复用脚本；`validate.py` 会校验该目录存在。

### 4.8 样本规模（D13）

- 本轮完成 8 道综合原题，生成 24 道变式；另有 2 道难度对照题、6 次注入。
- 说明书建议的“每模块 1 道普通题＋1 道综合题，共 16 题／48 道变式”只完成了综合题部分，普通题未做。
- 正式质量验收的 48 题方案未做。

### 4.9 学生版对比判断

- 被删答案的片段若也作为题面已知条件，出现在题干、小问、选项或材料中，不视为泄漏。例如答案“10 Ω”恰好是题干中的“R₁=10 Ω”。
- 出现在补写说明等其他保留内容中，仍判为泄漏。
- 这样调整是因为整段比对会漏掉片段泄漏，而对所有内容做片段比对又会误报题干。

## 5. 已知缺陷与限制

1. 宿主未实测（R12，阻断正式放行）：ChatGPT、Codex 的安装、确认交互、附件识别和文件回传均未运行。
2. Microsoft Word 未实测：只完成了 LibreOffice 渲染与往返。LibreOffice 下有两处显示与 Word 预期不同：
   - 带上标的单位（如 `\mathrm{m/s^2}`）中的字母显示为斜体，因为 LibreOffice 不遵守 OMML 的 `m:sty=p`。这是 0.8.1 数学转换器的既有行为，本次未改。
   - `\mathbf{R}` 显示为粗斜体。
   - 两处都需要在 Word 中确认。
3. 真实扫描件未测：合成样本的“原图”与转录同源，不能评估视觉识别准确率、复杂排版、低清公式和长 PDF。A01–A04 需用真实材料复测。
4. 普通题、长 PDF、跨批大题、表格内化学的成品样本缺失：这些逻辑有单元测试（跨批续做沿用 0.8.1 测试；表格内化学有 `ChemistryWordTests`），但没有端到端成品。
5. 学科正确性验证的边界：
   - 确定性检查只验证宿主写下的算式和方程，不能自动发现“题目本身设错但算式自洽”的情况，也无法判断题目的科学情境是否合理。
   - `roots` 用区间扫描找根，不覆盖区间外的根，也可能漏掉不变号的重根；重根只能由代入检查兜底。
   - `balance` 要求离子电荷写成 `^`，例如 `Fe^3+`。
6. 难度判断：脚本只校验难度标签与请求一致、依据已填写，不评估实际难度。
7. 学生包审计的启发式：
   - 疑似答案标签只覆盖常见中文标签。
   - 三个字以下的答案片段（如选项字母）不比对，由角色投影保证移除。
8. 台账和内部证据中含开发环境的绝对路径（如 `/home/claude/...`），复现时会在新位置重新生成。
9. 教材版次、册次、单元映射未内置（D02）：无法确认时如实标为未知。

## 6. 验收侧最短复现步骤

```sh
git clone https://github.com/MaybeGoodman/Scan-assistant && cd Scan-assistant
git checkout feat/1.0.0-v1-candidate          # 再核对交接消息中的精确 SHA
python -m pip install -r requirements-dev.txt
python scripts/validate.py
python -m unittest discover -s tests -v       # 期望 234 项通过
# 重建样本（可选；需要 LibreOffice 与 libreoffice-math）
python -X utf8 samples/v1/build_samples.py stage1
python -X utf8 samples/v1/build_samples.py stage2
cat samples/v1/out/summary.json
```

单项复现：
- **学生版泄漏**：用任意 `out/<模块>/internal/generation/internal/forbidden.json` 运行：

  ```sh
  python -X utf8 plugins/image-print-extractor/skills/image-print-extractor/scripts/docx_audit.py out/<模块>/variants/student.docx --forbidden <forbidden.json>
  ```

- **草稿门槛**：对 `samples/v1/work/M06/orig.reviewed.json` 运行 `variants.py init ... --question qM06`，应被拒绝，原因是“推断补写内容待复核”。
- **注入**：参照 `tests/test_v1_variants.py` 中 `SubjectCheckTests.test_injected_errors_by_subject`，以及 `build_samples.py` 中的 `extra_runs()`。

建议验收侧优先复测：
1. ChatGPT、Codex 端到端（P01、P02、G03）。
2. 在真实 Word 中编辑化学与数学并打印（W01–W03）。
3. 真实扫描件与长 PDF（A01–A04）。
4. 独立重解 24 道变式（G01），并另行挑选普通题。

上述各项通过前，候选版本不应正式放行（说明书第 10.4 节）。
