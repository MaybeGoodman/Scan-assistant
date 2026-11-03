# V1.0 八模块样本与实际成品

本目录所有题目、阅读语篇和变式均为本仓库原创，不含教材或试卷原文。样本页 `source-page.png` 是**合成扫描件**，由 `render_page.py` 绘制。页面上带有：
- 学校页眉、半透明推广水印、蓝色手写勾和批注、印刷答案与解析。
- M06 页面另有墨迹遮挡一个数字，用于测试推断补写和草稿。

合成样本用于开发自测。真实教材和试卷扫描件需由验收侧另行准备，并在 ChatGPT、Codex 中复测。

## 重建

```sh
python -X utf8 samples/v1/build_samples.py stage1   # 渲染页面、生成候选、运行提取流水线，插图处停在复核
python -X utf8 samples/v1/build_samples.py stage2   # 复核续做、补写确认、学生版、三变式生成与交付、渲染
```

- 插图复核结论在 `reviews/M01.json`、`reviews/M02.json`，由开发侧逐张对照原图裁片与重绘 PNG 后填写，哈希绑定实际产物。
- `content.py` 中是原题、印刷答案、变式和内部答案；`figures.py` 中是结构化绘图场景。
- 页面渲染使用 LibreOffice 24.2（需安装 `libreoffice-math`，否则 OMML 公式不显示），不等同于 Microsoft Word。

## 模块一览

| 模块 | 原题 | 结构 | 特殊点 |
|---|---|---|---|
| M01 初中数学 | 第18题 等腰三角形 | 3 问，（3）依赖（2） | 几何图重绘；变式按新数据重画比例正确的图 |
| M02 初中物理 | 第21题 欧姆定律 | 3 问，（3）依赖（1） | 电路图重绘（组件库）；变式配同一拓扑的电路图 |
| M03 初中化学 | 第16题 方程式计算 | 3 问链式依赖 | 带条件的化学方程式（OMML）；失败注入与部分交付 |
| M04 初中英语 | 第31–33题 阅读 | 共享语篇＋3 题 | 选项唯一与证据定位；多答案注入 |
| M05 高中数学 | 第19题 二次函数 | 3 问，（2）依赖（1） | 降低／提高难度对照；漏根注入 |
| M06 高中物理 | 第15题 多过程运动 | 3 问 | 墨迹遮挡→推断补写→草稿→复核→正式；草稿状态下拒绝生成 |
| M07 高中化学 | 第17题 原电池 | 3 问链式依赖 | 离子方程式、电极反应（富文本上下标）；电荷守恒校验 |
| M08 高中英语 | 第24–26题 推断阅读 | 共享语篇＋3 题 | 推断题证据句；三篇新语篇 |

## 每个模块目录 `out/<模块>/`

| 文件 | 内容 |
|---|---|
| `source-page.png` | 原始样本页（合成扫描件） |
| `original.docx`、`original-chat.md` | 原题版：保留印刷答案与解析，去除水印、页眉、手写 |
| `original-final.docx` | 仅 M06：复核确认后的正式版（`original.docx` 为带标记的草稿） |
| `original-student.docx`、`original-student-chat.md` | 原题学生版：移除答案与解析 |
| `variants/student.docx`、`variants/student-chat.md`、`variants/figures/` | 三道同类题的学生包（无答案） |
| `difficulty-easier/`、`difficulty-harder/` | 仅 M05：降低、提高难度各一道 |
| `variants-partial/` | 仅 M03：失败注入后的部分交付（2/3） |
| （无文件夹） | M02、M04、M05：单题注入错误被拦截，交付结论为 `blocked`，不生成任何学生文件；证据在 `internal/generation-inject/` 和 `summary.json` |
| `render/` | 上述 Word 文件的 PDF 与逐页 PNG（LibreOffice 渲染） |
| `internal/` | 开发证据：提取候选、复核报告、生成台账、冻结的候选（含答案）、`answer-key.md`、`forbidden.json`。**不属于学生包** |

`out/summary.json` 汇总每个模块的交付结论、各候选的验证状态、学生包审计结果和附加用例结果。
