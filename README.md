# 图片印刷体提取 · Scan Assistant

<img src="plugins/image-print-extractor/assets/logo.png" width="160" alt="插件图标">

面向教材、试题、讲义、扫描图片和 PDF 的 Codex 插件。按语义保留主体印刷内容，忽略手写及明确无关的广告、水印、品牌和宣传二维码，输出 Markdown、LaTeX、表格及插图；PDF 经用户确认后整理为可编辑 Word 文档。

## 安装

在已安装 Codex CLI 的终端运行：

```sh
codex plugin marketplace add MaybeGoodman/Scan-assistant
```

私有仓库需要当前 Git 环境具备读取权限。重启桌面应用，在插件目录选择 **Scan Assistant** 来源，找到“图片印刷体提取”并安装，然后在新任务中使用。

上传图片后输入：

```text
使用 $image-print-extractor 提取这张图片的印刷内容，忽略手写。
```

也可直接请求“提取图片中的印刷体”；宿主支持自动技能选择时会匹配本技能。

上传 PDF 后，可直接说“提取印刷体、去掉无关水印，整理成 Word”。如果只说“整理这份 PDF”，插件会先询问是否生成 Word；已明确需要时不会重复询问。明确不需要 Word 则直接输出提取内容。

## 更新

已从此 GitHub 来源安装的用户先运行 `codex plugin marketplace upgrade scan-assistant` 刷新来源，再在插件目录更新或重新安装“图片印刷体提取”，并开启新任务。当前功能版本为 `0.5.0`，见 [更新记录](CHANGELOG.md)。

## 化学输出

图片直接回复、PDF、正文、选项和表格中的化学表达统一为标准 LaTeX 源码。例如 N₂ 输出为 `\mathrm{N_2}`，SO₄²⁻ 输出为 `\mathrm{SO_4^{2-}}`；禁止 Unicode 上下标或 N2 等普通文本替代。默认用行内代码保护化学源码，中文正文正常输出。保留原图的等号、箭头、系数和反应条件，不自动配平或纠错。

## 行为

- 默认提取主体及相关支持内容的印刷体，不按答案、解析、注释分类删除；过滤范围与用户覆盖统一见 [主体内容筛选](plugins/image-print-extractor/skills/image-print-extractor/references/main-content.md)。正文标题、相关图注和来源保留，不确定时保留。
- 不解题、不改写、不摘要；恢复只基于可见笔画及排版结构，禁止上下文猜补，无法确认用 `XXX`，真实空白保持空白。
- 中文自然语言使用全角标点，数学/英文/代码保持语法；非 Word 数学输出用 `$...$` 或 `$$...$$`。
- 双栏先左后右；不额外添加标题、粗体或说明；图文表按原位置排列。
- HTML 模式的表格使用真实单元格和合并关系，可复制到 Word，公式仍为源码；需要数学原生公式时使用 `.docx` 导出模式。
- 先完成文字、公式和表格，再检测整份当前文档中的有效插图并询问一次是否重绘；提前明确要求图片也提取／重绘时不重复询问。拒绝默认不输出图片，明确原图要求才保留原图。
- 技术图优先按理解结构生成白底黑色 SVG 和高分辨率 PNG，普通教学示意插画可接入宿主图像生成能力。每张图必须与原图进行结构／标注校验，最多修正一次，失败原位提示且保留已完成文字；图片与 Word 确认独立。
- PDF 逐页处理，确认需要 Word 后生成实际 `.docx`，正文和表格可编辑，PNG 插图嵌入。
- Word 中数学公式经兼容 LaTeX 转为原生专业格式 OMML，支持段落及表格内混排；化学表达式单独保留可编辑 LaTeX 源码，不转 OMML、不依赖 `mhchem`/`\ce{}`。
- 恢复公式二维结构、行内/独立位置、函数名和单位字体；不自动化简、配平或纠错。无法判定或转换失败的表达式标记 `XXX`，内部复核记录保留原图位置和失败原因。
- 去掉确定无关的水印、推广字样等，恢复可靠的断行和跨页续句；不为通顺而改写事实，相关脚注、图注、来源说明仍保留。

## 运行条件与边界

一个核心 Skill 负责视觉识别和语义分类；select_content.py 执行宿主分类后的保守筛选并记录复核报告，本地导出脚本保持既有接口。脚本不是独立 OCR 或自主分类引擎，不会从候选文字执行命令或修改原图像素。基础转录需要支持图像输入的模型；文件导出需要 Python 3.10+ 和文件执行能力，像素裁剪另需 Pillow。HTML 导出仅用 Python 标准库，无外部 API、MCP、登录或网络服务依赖；安装插件不会自动安装 Python 包。

PDF 准备脚本使用 `pypdfium2` 和 Pillow，Word 导出使用 `python-docx`、Pillow、`lxml`，数学解析使用固定版本的 [latex2mathml](https://github.com/roniemartinez/latex2mathml)，随后由插件映射为 OMML。按需安装技能目录 `requirements.txt` 中的依赖。文本层只作为候选，扫描页由模型看图识别；水印和杂文字是否相关也由模型结合版面与语义判断，脚本不会按关键词批量删文。

数学转换使用明确的命令/结构白名单，不承诺完整 LaTeX。旧版 Word JSON 中的数学字符串须迁移为 `math` 类型；化学字符串须标为 `chemistry`，防止误转。接口、支持范围与异常处理见 [表达式规则](plugins/image-print-extractor/skills/image-print-extractor/references/formulas.md)。Word 导出同时写入内部 `.review.json`；缺少依赖会阻止导出，单式失败则记录位置并放置 `XXX`，交付前须复核。化学源码的后续渲染由接收环境处理。

HTML 是完整图文表结果；Markdown 在表格原位链接 HTML 表格。聊天窗口不支持富表格时不能保证直接复制为 Word 表格，需打开生成的 HTML。PNG／SVG 与 HTML 同目录分发，移动时保留 `figures/`。脚本不自动清除手写，识别质量依赖原图及宿主模型。

## 图片重绘开发接口与边界

当前有效需求见 [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md)，开发规则见 [AGENTS.md](AGENTS.md)。运行时按 [图片重绘流程](plugins/image-print-extractor/skills/image-print-extractor/references/figure-redraw.md) 使用 `figure_workflow.py plan / generate / complete`；结构化绘制由 `figure_drawing.py` 执行，复用 Pillow，不新增独立 OCR、绘图库或外部服务依赖。

新图片任务通过 `figure_task` 接入原有 blocks，检测、分类及源结构由宿主看图提供，导出前必须完成图片模式和视觉复核。旧版已复核 JSON 仍支持原 PNG 导出；这只是接口兼容，不覆盖新任务的 ignore／preserve／redraw 规则。自动结构检查和复核哈希仅验证已声明结构及具体产物，不能独立证明视觉理解或所有科学关系正确。中文标注需可用中文字体；复杂照片不属于首阶段核心范围。Word 嵌入兼容 PNG，独立 SVG 可编辑，不宣称 PNG 为 Word 原生绘图对象。

## 仓库结构

```text
.agents/plugins/marketplace.json
plugins/image-print-extractor/
  plugin.json
  .codex-plugin/plugin.json
  assets/
  skills/image-print-extractor/
    SKILL.md
    agents/openai.yaml
    references/
    scripts/
    assets/
tests/
scripts/validate.py
```

采用根目录 Agent Plugins 清单及 OpenAI 扩展，并保留 Codex 兼容清单。依据 2026-09-25 核对的 [OpenAI 插件打包文档](https://developers.openai.com/plugins/build/plugins)。GitHub 仓库分发不等于在官方公共插件目录上架。

## 开发验证

```sh
python -m pip install -r requirements-dev.txt
python scripts/validate.py
python -m unittest discover -s tests -v
```

测试还覆盖主体筛选、范围覆盖、UNKNOWN 保留、重叠保护、手写单元格清空及筛选到 HTML/DOCX 的完整流程；18 个语义场景使用已标注候选，不能替代模型看图分类测试。测试覆盖 HTML 转义、合并单元格、空白、图文顺序、PNG、路径限制、不覆盖已有输出，以及 OMML 二维结构、字体、混排、化学源码和转换失败。识别行为及 Word 应用验收见 [验收清单](docs/acceptance.md)，自动化测试不代表 OCR 准确率或所有 Word 版本的排版保证。

本次规则冲突处理与验证边界见 [0.4.0 更新核对](docs/main-content-update.md) 和 [测试报告](docs/main-content-test-report.md)。

0.5.0 差异分析、兼容性和验证边界见 [图片重绘开发记录](docs/figure-redraw-development.md)。受控绘图样例可用 `python tests/generate_figure_cases.py --output <目录>` 生成，不能替代真实扫描和宿主新会话验收。

图标与 Logo 由仓库所有者提供，原文件直接复制。未替所有者指定开源许可证。
