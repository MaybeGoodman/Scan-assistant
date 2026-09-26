# 图片印刷体提取 · Scan Assistant

<img src="plugins/image-print-extractor/assets/logo.png" width="160" alt="插件图标">

面向教材、试题、讲义、扫描图片和 PDF 的 Codex 插件。保留印刷内容，忽略手写、无关水印和杂文字，输出 Markdown、LaTeX、表格及插图；PDF 经用户确认后整理为可编辑 Word 文档。

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

已从此 GitHub 来源安装的用户先运行 `codex plugin marketplace upgrade scan-assistant` 刷新来源，再在插件目录更新或重新安装“图片印刷体提取”，并开启新任务。当前功能版本为 `0.3.0`，见 [更新记录](CHANGELOG.md)。

## 行为

- 所有印刷内容默认保留，不按答案、解析、注释分类删除；手写及无关页眉页脚排除。
- 不解题、不改写；局部内容只能在可靠时恢复，否则用 `XXX`；真实空白保持空白。
- 中文自然语言使用全角标点，数学/英文/代码保持语法；非 Word 数学输出用 `$...$` 或 `$$...$$`。
- 双栏先左后右；不额外添加标题、粗体或说明；图文表按原位置排列。
- HTML 模式的表格使用真实单元格和合并关系，可复制到 Word，公式仍为源码；需要数学原生公式时使用 `.docx` 导出模式。
- 插图提取为实际 PNG；图内手写须由宿主可用图像工具处理并复核，无法可靠恢复时说明缺项。
- PDF 逐页处理，确认需要 Word 后生成实际 `.docx`，正文和表格可编辑，PNG 插图嵌入。
- Word 中数学公式经兼容 LaTeX 转为原生专业格式 OMML，支持段落及表格内混排；化学表达式单独保留可编辑 LaTeX 源码，不转 OMML、不依赖 `mhchem`/`\ce{}`。
- 恢复公式二维结构、行内/独立位置、函数名和单位字体；不自动化简、配平或纠错。无法判定或转换失败的表达式标记 `XXX`，内部复核记录保留原图位置和失败原因。
- 去掉确定无关的水印、推广字样等，恢复可靠的断行和跨页续句；不为通顺而改写事实，相关脚注、图注、来源说明仍保留。

## 运行条件与边界

一个核心 Skill 负责视觉识别和决策；本地脚本负责确定性导出，不是独立 OCR 引擎。基础转录需要支持图像输入的模型；文件导出需要 Python 3.10+ 和文件执行能力，像素裁剪另需 Pillow。HTML 导出仅用 Python 标准库，无外部 API、MCP、登录或网络服务依赖；安装插件不会自动安装 Python 包。

PDF 准备脚本使用 `pypdfium2` 和 Pillow，Word 导出使用 `python-docx`、Pillow、`lxml`，数学解析使用固定版本的 [latex2mathml](https://github.com/roniemartinez/latex2mathml)，随后由插件映射为 OMML。按需安装技能目录 `requirements.txt` 中的依赖。文本层只作为候选，扫描页由模型看图识别；水印和杂文字是否相关也由模型结合版面与语义判断，脚本不会按关键词批量删文。

数学转换使用明确的命令/结构白名单，不承诺完整 LaTeX。旧版 Word JSON 中的数学字符串须迁移为 `math` 类型；化学字符串须标为 `chemistry`，防止误转。接口、支持范围与异常处理见 [表达式规则](plugins/image-print-extractor/skills/image-print-extractor/references/formulas.md)。Word 导出同时写入内部 `.review.json`；缺少依赖会阻止导出，单式失败则记录位置并放置 `XXX`，交付前须复核。化学源码的后续渲染由接收环境处理。

HTML 是完整图文表结果；Markdown 在表格原位链接 HTML 表格。聊天窗口不支持富表格时不能保证直接复制为 Word 表格，需打开生成的 HTML。PNG 与 HTML 同目录分发，移动时保留 `figures/`。脚本不自动清除手写，识别质量依赖原图及宿主模型。

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

测试覆盖 HTML 转义、合并单元格、空白、图文顺序、PNG、路径限制、不覆盖已有输出，以及 OMML 二维结构、字体、混排、化学源码和转换失败。识别行为及 Word 应用验收见 [验收清单](docs/acceptance.md)，自动化测试不代表 OCR 准确率或所有 Word 版本的排版保证。

图标与 Logo 由仓库所有者提供，原文件直接复制。未替所有者指定开源许可证。
