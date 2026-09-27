# 表达式识别与导出

## 内容判定与忠实扫描

本规则同时适用于图片和 PDF、正文与表格。数学和物理计算式走数学路线；化学式、离子式、反应式走化学路线。同一段内可以混排，按表达式边界分类，不能只凭学科或整页标题决定。元素符号或单个字母含义不清时回看原图和上下文，不根据字符串自动猜测类别。

优先恢复二维结构和语义归属：分数线的上下区域、根号覆盖范围、上下标层级、括号配对、向量标记、矩阵的行列，以及反应条件相对于箭头的位置。不可将上下排列的内容平铺成普通文字。保持行内与独立公式、原文顺序、换行、对齐和编号关系；单个变量可以是行内公式，不全部另起一段。

任务是还原。清晰的数学错误、未配平反应、异常价态仍照录，不求解、化简、改写、配平或纠错。仅在字符明显缺失且可依据可见笔画、版面和上下文唯一、高置信度确定时补充，内部记录位置和依据。不能可靠判定时使用最小粒度 `XXX`；已知部分仍保留结构，如 `\frac{\text{XXX}}{y}`。真实空白不是识别失败，不填 `XXX`。

## 数学：LaTeX → OMML

用规范 LaTeX 作为内部中间表示。Word 中必须生成原生专业格式 OMML，可用 Word 自带公式编辑器直接修改、复制、保存和打印，不依赖 AxMath 或 MathType。最终 Word 正文和表格中的数学公式不得残留 LaTeX/UnicodeMath 源码，不得改为图片或用普通文本模拟二维结构。

变量通常斜体；函数和运算符用 `\sin`、`\cos`、`\ln`、`\operatorname{...}` 等正体名称；单位用 `\mathrm{kg}`、`\mathrm{m/s}`，说明文字包括中文用 `\text{...}`。向量或特殊字体忠实保留原文含义，不自动增加原图没有的标记。

随附 `scripts/formulas.py` 用固定版本 `latex2mathml` 解析，再映射为原生 OMML。它不调用 Word 的 LaTeX 输入模式，也不执行 TeX、加载用户宏或联网。插件所称“Word 兼容”是经过此转换链验证的子集，不承诺完整 LaTeX 或任意 Word 版本的线性输入语法。

主要支持范围：

| 结构 | 建议写法 |
| --- | --- |
| 分式、根式、上下标 | `\frac{a}{b}`、`\sqrt[n]{x}`、`x_i^2` |
| 括号、绝对值 | `\left( ... \right)`、`\left| ... \right|` |
| 向量、横线、重音 | `\vec{v}`、`\overline{AB}`、`\hat{x}` |
| 求和、积分、极限 | `\sum_{i=1}^{n}i`、`\int_0^1 x\,\mathrm{d}x`、`\lim_{x\to0}f(x)` |
| 矩阵 | `matrix`、`pmatrix`、`bmatrix`、`Bmatrix`、`vmatrix`、`Vmatrix` 环境 |
| 分段函数 | `\begin{cases}x^2&x>0\\0&x\leq0\end{cases}` |
| 多行推导、方程组 | `aligned`、`gathered` 或 `array` 环境；列分隔用 `&`，行分隔用 `\\` |
| 字体、集合、常用符号 | `\mathrm`、`\mathit`、`\mathbf`、`\mathbb`、`\mathcal`，常用希腊字母及集合/关系符号 |

完整命令白名单由 `MATH_COMMANDS`、`ENVIRONMENTS` 定义，转换器同时拒绝未知结构和不支持的间距。`aligned` 转为左右对齐列，`gathered` 转为单列；`array` 使用明确的 `l`、`c`、`r` 列格式。需要伸缩的括号显式使用 `\left`/`\right`；上下限在原图位于上下方或右侧时，分别用 `\limits`、`\nolimits` 明确位置。独立公式中的极限默认下置，行内默认右侧下标。超出范围时，只能在不改变表达式的前提下重写为已支持的等价排版，不能绕过校验或用图片回退。

## 化学：保留 LaTeX 源码

最终 Word 中的化学内容为可复制、修改的 LaTeX 文本，反斜杠和花括号原样保留，不是渲染后的 Word 公式。非 Word 输出也保留源码，使用行内代码或代码块防止宿主自动渲染；默认不把数学公式的 `$...# 表达式识别与导出

## 内容判定与忠实扫描

本规则同时适用于图片和 PDF、正文与表格。数学和物理计算式走数学路线；化学式、离子式、反应式走化学路线。同一段内可以混排，按表达式边界分类，不能只凭学科或整页标题决定。元素符号或单个字母含义不清时回看原图和上下文，不根据字符串自动猜测类别。

优先恢复二维结构和语义归属：分数线的上下区域、根号覆盖范围、上下标层级、括号配对、向量标记、矩阵的行列，以及反应条件相对于箭头的位置。不可将上下排列的内容平铺成普通文字。保持行内与独立公式、原文顺序、换行、对齐和编号关系；单个变量可以是行内公式，不全部另起一段。

任务是还原。清晰的数学错误、未配平反应、异常价态仍照录，不求解、化简、改写、配平或纠错。仅在字符明显缺失且可依据可见笔画、版面和上下文唯一、高置信度确定时补充，内部记录位置和依据。不能可靠判定时使用最小粒度 `XXX`；已知部分仍保留结构，如 `\frac{\text{XXX}}{y}`。真实空白不是识别失败，不填 `XXX`。

## 数学：LaTeX → OMML

用规范 LaTeX 作为内部中间表示。Word 中必须生成原生专业格式 OMML，可用 Word 自带公式编辑器直接修改、复制、保存和打印，不依赖 AxMath 或 MathType。最终 Word 正文和表格中的数学公式不得残留 LaTeX/UnicodeMath 源码，不得改为图片或用普通文本模拟二维结构。

变量通常斜体；函数和运算符用 `\sin`、`\cos`、`\ln`、`\operatorname{...}` 等正体名称；单位用 `\mathrm{kg}`、`\mathrm{m/s}`，说明文字包括中文用 `\text{...}`。向量或特殊字体忠实保留原文含义，不自动增加原图没有的标记。

随附 `scripts/formulas.py` 用固定版本 `latex2mathml` 解析，再映射为原生 OMML。它不调用 Word 的 LaTeX 输入模式，也不执行 TeX、加载用户宏或联网。插件所称“Word 兼容”是经过此转换链验证的子集，不承诺完整 LaTeX 或任意 Word 版本的线性输入语法。

主要支持范围：

| 结构 | 建议写法 |
| --- | --- |
| 分式、根式、上下标 | `\frac{a}{b}`、`\sqrt[n]{x}`、`x_i^2` |
| 括号、绝对值 | `\left( ... \right)`、`\left| ... \right|` |
| 向量、横线、重音 | `\vec{v}`、`\overline{AB}`、`\hat{x}` |
| 求和、积分、极限 | `\sum_{i=1}^{n}i`、`\int_0^1 x\,\mathrm{d}x`、`\lim_{x\to0}f(x)` |
| 矩阵 | `matrix`、`pmatrix`、`bmatrix`、`Bmatrix`、`vmatrix`、`Vmatrix` 环境 |
| 分段函数 | `\begin{cases}x^2&x>0\\0&x\leq0\end{cases}` |
| 多行推导、方程组 | `aligned`、`gathered` 或 `array` 环境；列分隔用 `&`，行分隔用 `\\` |
| 字体、集合、常用符号 | `\mathrm`、`\mathit`、`\mathbf`、`\mathbb`、`\mathcal`，常用希腊字母及集合/关系符号 |

完整命令白名单由 `MATH_COMMANDS`、`ENVIRONMENTS` 定义，转换器同时拒绝未知结构和不支持的间距。`aligned` 转为左右对齐列，`gathered` 转为单列；`array` 使用明确的 `l`、`c`、`r` 列格式。需要伸缩的括号显式使用 `\left`/`\right`；上下限在原图位于上下方或右侧时，分别用 `\limits`、`\nolimits` 明确位置。独立公式中的极限默认下置，行内默认右侧下标。超出范围时，只能在不改变表达式的前提下重写为已支持的等价排版，不能绕过校验或用图片回退。

## 化学：保留 LaTeX 源码

最终 Word 中的化学内容为可复制、修改的 LaTeX 文本，反斜杠和花括号原样保留，不是渲染后的 Word 公式。非 Word 输出也保留源码，使用行内代码或代码块防止宿主自动渲染； 分隔符套到化学源码上；用户明确要求渲染时可使用数学分隔符，源码规范仍适用。

- 元素正体，原子数为下标，离子电荷、同位素、氧化态按原文上标位置表示；氧化数位于元素上方时用 `\overset`，不误放到整个离子右上角。
- 保留系数、括号层级、化学状态、结晶水连接点、电子及电子转移关系。
- 保留单向/反向/可逆箭头及气体、沉淀标记；记录反应条件在箭头上方还是下方，不将条件移到反应式末尾。
- 优先常用 LaTeX，不使用 `mhchem`、`\ce{}`、自定义宏或宏包加载命令。上下条件可用 `\overset`、`\underset` 或 `\xrightarrow[下方]{上方}`。这些扩展命令只被作为源码保存，后续若要渲染，须由目标环境提供相应支持（如 `amsmath` 和中文字体）；本插件不承诺纯 LaTeX 核心即可渲染所有条件。

规范化检查适用于图片直接回复、Markdown、HTML 和 Word，不限于独立反应式。元素大小写依据原图，不根据“常见化学式”纠错；电子式和结构式保留点、键、括号及其二维位置，无法判定的局部用 \text{XXX}。

| 原图内容 | LaTeX 源码 |
| --- | --- |
| N₂ / 2N₂ | `\mathrm{N_2}` / `2\mathrm{N_2}` |
| Na⁺ / Ca²⁺ / NH₄⁺ | `\mathrm{Na^+}` / `\mathrm{Ca^{2+}}` / `\mathrm{NH_4^+}` |
| SO₄²⁻ | `\mathrm{SO_4^{2-}}` |
| ²³₁₁Na | `{}^{23}_{11}\mathrm{Na}` |
| H⁺ + OH⁻ = H₂O | `\mathrm{H^+}+\mathrm{OH^-}=\mathrm{H_2O}` |
| CaCO₃(s) / AgCl↓ / CO₂↑ | `\mathrm{CaCO_3(s)}` / `\mathrm{AgCl}\downarrow` / `\mathrm{CO_2}\uparrow` |
| KClO₃ 分解，上方 MnO₂、下方加热 | `2\mathrm{KClO_3}\xrightarrow[\Delta]{\mathrm{MnO_2}}2\mathrm{KCl}+3\mathrm{O_2}` |

只有原图确实印有对应系数、符号和条件时才使用示例中的完整表达式。N2、H2SO4、SO42-、N₂、SO₄²⁻ 均不能作为化学最终输出，即使包在 \mathrm{...} 内也不合格。数字根据原图语义定位，不对整页文字做正则替换。

混排示例（数学变量仍沿用数学格式）：

1 g `\mathrm{N_2}` 中含有 $n$ 个 `\mathrm{N_2}` 分子。

更多结构示例：

```latex
\mathrm{H_2SO_4}
\mathrm{SO_4^{2-}}
\mathrm{CuSO_4}\cdot 5\mathrm{H_2O}
{}^{14}_{6}\mathrm{C}
\mathrm{H_2(g)}
\mathrm{Fe^{2+}}\rightarrow\mathrm{Fe^{3+}}+\mathrm{e^-}
\mathrm{[Fe(CN)_6]^{3-}}
\mathrm{Fe^{3+}}+3\mathrm{OH^-}\rightarrow\mathrm{Fe(OH)_3}\downarrow
2\mathrm{H_2}+\mathrm{O_2}\xrightarrow{\text{点燃}}2\mathrm{H_2O}
\mathrm{N_2}+3\mathrm{H_2}\overset{\text{催化剂}}{\underset{\text{高温、高压}}{\rightleftharpoons}}2\mathrm{NH_3}
```

示例不构成自动配平依据。原文 `H₂ + O₂ → H₂O` 必须保留为 `\mathrm{H_2}+\mathrm{O_2}\rightarrow\mathrm{H_2O}`。

## JSON 表达式接口

正文和表格单元格可提供 `text` 或 `runs`，两者互斥。普通文字继续用 `text`。含表达式时用有序 `runs`，每项显式标记 `text`、`math` 或 `chemistry`；独立表达式使用顶层 `math`/`chemistry` 块。表达式的 `latex` 字段不包含 `$`、`$$`、`\(` 等外层分隔符。JSON 内反斜杠写为 `\\`。

```json
{"blocks":[
  {"type":"text","source":{"page":1,"bbox":[20,30,500,70]},"runs":[
    {"type":"text","text":"已知 "},
    {"type":"math","latex":"x^2+\\frac{1}{y}"},
    {"type":"text","text":"，物质为 "},
    {"type":"chemistry","latex":"\\mathrm{H_2SO_4}"}
  ]},
  {"type":"math","id":"p1-e2","source":{"page":1,"bbox":[20,80,500,160]},
   "latex":"\\begin{cases}x^2&x>0\\\\0&x\\leq0\\end{cases}"},
  {"type":"chemistry","latex":"\\mathrm{H_2}+\\mathrm{O_2}\\rightarrow\\mathrm{H_2O}"},
  {"type":"table","rows":1,"cols":2,"cells":[
    {"row":0,"col":0,"runs":[{"type":"math","latex":"a_1"}]},
    {"row":0,"col":1,"runs":[{"type":"chemistry","latex":"\\mathrm{Fe^{3+}}"}]}
  ]}
]}
```

可选表达式字段：`id` 标识、`source` 原图定位、`confidence` 识别置信度、`repairs` 补充记录列表。`source` 建议包含从 1 开始的页码及对应页面图像中的像素框 `[左,上,右,下]`。行内项未写 `source` 时继承所在段落/单元格/表格的定位；仍缺失时，报告至少保留 JSON 块和 run 索引。

能保留局部结构时在 `latex` 内写 `\text{XXX}`；整式无法判定时使用 `"status":"unresolved"` 并在 `reason` 说明原因。真实空白用空 `text`，不伪装成空公式。

旧版 Word JSON 中的 `$...$` 字符串必须由识别阶段迁移为有类型的表达式，导出器不会猜测其是数学还是化学。发现遗留数学源码时导出报错，避免交付错误格式。原有纯文字、图形和表格结构仍兼容；HTML 导出也支持新结构，数学保留带分隔符的源码，化学保留原始源码。

## 异常与验证

表达式语法或转换失败时，Word 在该表达式位置放置 `XXX`，其他已知内容继续输出；原始 LaTeX、失败原因和位置写入同名 `.review.json`，不塞进最终 Word。已含局部 `XXX`、有恢复记录或标为 `unresolved` 的表达式也进入待复核记录。缺少依赖、输入结构错误或文件写入失败应说明具体问题，不用整页 `XXX` 假装识别完成。

生成 Word 后读取 `.review.json` 并回看原图，修复可可靠修复的项目；不得把包含失败占位符的文档描述为全部转换成功。核查 OMML 的分式、根式、上下标、矩阵行列、对齐、字体，确认化学内容仅在普通文字节点中。按 PDF/Word 流程渲染并逐页复核；最终在 Word 中验证保存、复制、修改、打印。日志放在工作目录，仅应用户要求交付。

导出器对显式 chemistry 内容执行基本 LaTeX 语法和常见非规范写法校验，不自动识别普通 text 中的化学语义，也不验证配平或化学正确性。Word 不合格表达进入 XXX 和复核记录（含表格），HTML/Markdown 导出报错并在写文件前停止；回看原图后修复输入。聊天回复由技能规则和交付复核保障，脚本校验不等同于视觉识别验收。
