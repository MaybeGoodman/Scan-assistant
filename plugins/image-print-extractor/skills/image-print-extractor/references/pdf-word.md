# PDF 提取与 Word 输出

## 先明确输出方式

- “把 PDF 转为 Word”“整理成 docx”以及本任务已明确的 Word 要求，均是确认，不再询问。
- 只上传 PDF，或只说“提取/整理内容”：先问“这份 PDF 是否需要整理为 Word（.docx）文档？”提供“生成 Word / 直接输出提取内容”两种选择，等明确答复。
- “可以”“是”作为该问题的直接回答视为确认；不清楚的答复继续澄清。不要根据文件长短或内容自行代替用户决定。
- 明确不要 Word 时继续 PDF 识别及去干扰，按普通 Markdown/富内容方式输出。混合附件只确认一次适用于本次 PDF 的格式；不擅自把多个独立文件合并到一个 Word。

## 逐页读取

优先用宿主现有 PDF 阅读工具。无专用工具时，用随附脚本生成页面 PNG 和文本层候选；只处理用户指定的页时加 `--pages`（从 1 开始，如 `3-5,8`）：

```text
python <skill-dir>/scripts/prepare_pdf.py input.pdf --output-dir work/pdf-pages --pages 3-10
```

默认 200 DPI（范围 72–400）。文件名和 `pages.json` 中的 `page` 均为原 PDF 页码。小字号公式或上下标看不清时，用局部重渲染放大查看后再判断，不凭上下文猜补；该图只供识别，不作为交付插图：

```text
python <skill-dir>/scripts/render_pdf_region.py input.pdf --page 3 --box 100 200 600 500 --base-dpi 200 --dpi 400 --output work/zoom-p3-1.png
```

`--box` 为 `--base-dpi` 渲染图（即 pages.json 中对应 PNG）上的像素坐标。

依赖 `pypdfium2`、Pillow；所有脚本依赖列于技能内 `requirements.txt`，只按当前模式需要安装。脚本不是 OCR，不判断手写或水印。`pages.json` 的 `text_candidate` 只能辅助定位，不能直接作为最终正文：扫描 PDF 可能没有文本层，有文本层也可能错误、含手写识别或水印。

逐页查看 PNG，先执行 [主体内容筛选](main-content.md)，再依原有印刷体规则提取。按页序处理，页内双栏先左后右。临时记录已处理页、被过滤元素和不确定片段，供复核，不塞入最终 Word。加密或损坏 PDF 无法读取时说明具体障碍，不跳过页面假装完成。

### 长 PDF 分批与续做

本次需处理的页超过 5 页时，必须分批处理并登记进度：

```text
python <skill-dir>/scripts/pdf_batches.py init work/pdf-pages/pages.json --progress work/progress.json --batch-size 5
python <skill-dir>/scripts/pdf_batches.py status work/progress.json
python <skill-dir>/scripts/pdf_batches.py commit work/progress.json --batch 1 --blocks work/batch-01.json
python <skill-dir>/scripts/pdf_batches.py merge work/progress.json --output work/candidates.json
```

1. `init` 按页序切分批次（默认每批 5 页，最多 20）。
2. 每批：查看该批页面 → 主体筛选和识别 → 写 `batch-NN.json`（`{"batch":N,"pages":[...],"blocks":[...],"figures":[...]}`）→ `commit`。`blocks` 与候选 JSON 结构相同，可带 selection；`figures` 与 `figure_task.figures` 单项结构相同，`source_page` 为原页码，本批无插图时省略。
3. 每次 commit 后看输出的 `complete`；只要为 false 就继续 `next_batch`，不得只处理前几页就输出结果。
4. 全部完成后 `merge` 得到 candidates.json；有插图时自动生成 `scan_complete:true` 的 `figure_task`。再进入 SKILL.md 中的导出流程。

block id 使用 `p<页码>-<序号>`，如 `p3-1`，合并时 id 冲突会报错。一段文字跨批次时，仅在视觉和结构能确认是同一句时，在后一批首个 text block 上加 `"join_previous": true`。批次文件和合并输出放在 progress.json 同一目录内；提交后不得再改批次文件，合并会校验哈希。

会话中断后继续时，先运行 `status`，从 `next_batch` 继续，不重做已完成批次。工作目录在本次会话不可访问时，说明需要重新处理，不假装续做。

## 去干扰并恢复语句

过滤类别、用户覆盖、保守保留及水印覆盖规则统一见 [主体内容筛选](main-content.md)，不得将文本层当作已筛选正文。

只根据可见笔画及结构接回可确认同一句的断行或跨页续文，修复经原图确认的 OCR 重复及断词。保留真实段落、选项、题目、列表及公式边界。英文行末连字符只有确定为排版断词时才移除；原本的连字符词保留。不依据上下文补写被遮挡内容，无法确认时局部 `XXX`，真实空白保持空白。

## 生成实际 Word

先把已复核、已去干扰的结果整理为 [富内容输出](rich-output.md) 中的 `blocks` JSON；含表达式时同时按 [表达式接口](formulas.md) 分类为数学或化学，使用 `runs` 或独立表达式块。合并跨页续句在此阶段完成，导出器不自动猜测或删字。每个 `text` 块对应一个段落；其内换行保留为段内换行。表格用完整单元格及合并跨度。先输出已完成文字／公式／表格；全部 PDF 页面检测后按 [图片重绘](figure-redraw.md) 仅确认一次，并在对应原位置放入经校验的重绘 PNG、明确保留的原图或失败占位。image_mode=ignore 时不插图。完成图片任务后再生成最终 Word。

图片授权与 Word 授权独立：已明确 Word 的任务不重复确认格式，图片回答是不能自动视为需要 Word；图片处理失败也不撤销已完成文字及 Word 输出选择。

确认用户需要 Word 后执行：

```text
python <skill-dir>/scripts/export_docx.py reviewed.json --output result.docx --report work/result.review.json --word-confirmed
```

`--word-confirmed` 只用于记录已得到的用户选择，不得替代真实确认。导出器需要 `python-docx`、Pillow、`lxml`；数学转换另需 `latex2mathml`。保留可编辑文字、原生 Word 表格及嵌入图片，不用整页扫描图代替正文。数学公式经 LaTeX 转换为原生可编辑 OMML，化学表达式保留 LaTeX 源码文本。二者均不能用图片替代。

导出后读取复核 JSON；语法/转换失败、识别不确定或有补充记录的项目必须回看原图。转换失败位置为 `XXX`，原始源码只留在内部记录。依赖缺失或输入结构错误会阻止导出，应解决具体问题，不能声称已完成。`--report` 未指定时报告与 Word 同名，扩展名为 `.review.json`；两个文件均禁止覆盖已有文件。

默认单栏、清楚的中文字体与适当页边距，不逐页强制复制原 PDF 分页，不添加封面、目录、总结或源文件不存在的标题。必要的分页按阅读与表格完整性调整。用户要求具体模板时优先遵循。

打开生成文件核对段落顺序、表格合并、空白格、公式、插图及页覆盖。用宿主可用的 DOCX 渲染器逐页检查，修复溢出、遮挡、缺字和不合理断页后交付。若缺少渲染器，至少重新读取 DOCX 内容和结构，明确说明未完成视觉验证，不宣称排版已验证。清理规则针对输出文档，不修改原 PDF。

交付最终 `.docx` 下载链接，不附整份 JSON、OCR 日志或页面 PNG，除非用户要求。没有文件生成能力时说明限制，不改成交付 HTML 冒充 Word。
