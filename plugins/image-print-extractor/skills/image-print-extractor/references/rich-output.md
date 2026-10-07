# 表格与图形

## 表格

保留行列、空白格、多级表头、跨行跨列及内容位置。只含手写的格清空但格保留；确有无法辨认的印刷内容才填 `XXX`。表达式按 [数学与化学规则](formulas.md) 分类；Word 表格内数学转 OMML，化学保留 LaTeX 源码。

不要输出管道形式的 Markdown 表格源码、截图表格或用空格排出的伪表格。宿主支持可编辑富表格时直接呈现；否则使用随附 `scripts/export_page.py` 生成 HTML 文件，打开或预览渲染结果，并提供简短文件链接。浏览器中的 HTML 表格可以选择并复制到 Word，或用 Word 打开 HTML；具体剪贴板行为由宿主决定，不承诺任意聊天窗口都能直接粘贴为表格。合并单元格用真实 `rowspan`、`colspan`。

按 [主体内容筛选](main-content.md) 复核并筛选候选，将结果写成 UTF-8 JSON。`blocks` 按阅读顺序排列；候选含 selection 时必须先运行 select_content.py，不能直接交给导出器。纯文字用 `text`；包含行内表达式时改用有类型的 `runs`，独立公式使用 `math` 或 `chemistry` 块；详见 [表达式接口](formulas.md)。JSON 反斜杠写作 `\\`。例如：

```json
{"blocks":[
  {"type":"text","runs":[{"type":"text","text":"已知 "},{"type":"math","latex":"a>0"},{"type":"text","text":"，填写下表。"}]},
  {"type":"table","rows":2,"cols":2,"cells":[
    {"row":0,"col":0,"text":"项目"},
    {"row":0,"col":1,"text":"数值"},
    {"row":1,"col":0,"text":"A"},
    {"row":1,"col":1,"text":""}
  ]},
  {"type":"image","path":"figure-01.png","alt":""}
]}
```

每个可见单元格都需列出，包括空格；被合并覆盖的位置不再列出。索引从零开始；`rowspan`、`colspan` 默认为 1。图路径相对 JSON 所在文件夹，仅允许该文件夹内的 PNG。

```text
python <skill-dir>/scripts/export_page.py page.json --output-dir result
```

脚本生成 `result.html`、`result.md` 和 `figures/`。HTML 是保留图文表顺序的完整富内容版，公式保留可复制的 LaTeX 源码，不依赖在线公式渲染。Markdown 在表格原位置放置 HTML 表格链接；不声称 Markdown 本身含原生表格。交付时优先打开 HTML 预览并链接，普通文字仍可直接回复。相对图片链接用于可移动的文件包；聊天内展示图片时转成当前宿主支持的真实附件或绝对路径。

## 图形

先记录插图、几何图、示意图、坐标图、流程图的区域和正文关联，完成文字／表格后执行 [图片识别与黑白重绘](figure-redraw.md) 的任务级确认。默认不直接交付原图；ignore 不输出图片，preserve 仅用于明确保留原图，redraw 生成白底黑色规范图并校验。图内结构性标签不重复转录；图外图题和图注在其原位置保留。图片任务通过 figure_workflow.py 完成后再导出；结构化图的 SVG 配套保存，原导出接口仍以 PNG 插入 HTML／Word。

以下裁剪及原图清理规则仅用于私有理解依据或用户明确选择的 preserve，不等同重绘：从源图精确提取 PNG，保留原图背景，不默认透明化，提取后查看实际文件。

宿主允许本地像素裁剪时，可使用：

```text
python <skill-dir>/scripts/crop_png.py source.png figure-01.png --box 100 200 600 700
```

坐标为经过 EXIF 方向校正后的像素坐标，左、上包含，右、下不包含。裁剪脚本只裁剪，不识别或去除手写。不能把脚本输出自动认定为干净原图。

手写处在外围时通过裁剪排除；图内手写需用可用且获准的图像编辑工具清除，并对照原图确认未改变印刷线条、数值及位置。不得仅按颜色阈值批量抹除，不得生成一个“看起来合理”的替代图。无法可靠恢复被遮挡结构时，不交付仍含手写的图并声称完成；简短说明该图缺项或请求清晰原图，保留其他已完成内容。

导出脚本不调用 OCR、网络或模型 API；识别、阅读顺序和干净图形判定由宿主模型完成。

## Word 分页关联

导出器默认保持单个段落完整，并对相邻的题干、插图和连续 A–H 选项设置分页关联，题组末端解除关联，避免整份文档被串成一组。很长的题组仍可能跨页，必须查看实际渲染页。复杂题组可在文字、公式或图片块中使用 `"layout":{"keep_with_next":true,"keep_together":true,"page_break_before":false}` 明确关系；字段只能为布尔值，显式设置覆盖自动关联。不要因分页重写题干、改变数值或把公式转成图片。
