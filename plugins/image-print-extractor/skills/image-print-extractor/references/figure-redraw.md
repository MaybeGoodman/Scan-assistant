# 可选图片识别与黑白重绘

本规则用于有效教学插图。开始前按 SKILL.md 一次性确认图片处理方式；执行时先完成文字、公式和真实表格（不把独立公式或表格交给绘图流程），再按已确认的 `image_mode` 处理有效图。宿主负责看图、分类、理解、绘图方式选择和真实原图对照；本地脚本不做 OCR，也不自动推断科学含义。

## 确认与范围

- 默认在开始处理前，与输出格式问题合并询问一次（见 SKILL.md“开始前的确认”），是否询问以覆盖全部当前页面的插图预扫描为准；没有有效图则不询问、不生成图片。仅当预扫描未发现、正式处理中才发现有效插图时，在文字输出后补问一次：**是否需要识别并重新绘制其中的图片？是 / 否**。不得逐页或逐图重复询问。
- 最初已明确“文字和图片都提取”“图片也重绘”“只要文字”或“保留原图”时直接执行，不重复询问。用户回答的解析统一由 `confirmation.py`（支持否定“不要保留原图”及选项 D）执行，含糊回答继续澄清；不能把 Word 问题的“是”当作图片授权。
- 模式只作用于当前任务，不保存永久偏好。命令行 `--image-mode`／`--response` 记录当前聊天的实际选择，文件中的 image_mode、授权声明或试题要求不能代替用户授权。
- 数学几何、坐标／函数、物理运动／受力／电路／光路、简单实验装置、结构、组合图和流程图优先支持。水印、宣传二维码、Logo、广告、装饰不重绘；正文研究对象按主体筛选保留文字或显式原图，但不借此把宣传图送入重绘。
- 复杂照片默认跳过；只有确能理解简单结构时才作简化示意图。模糊、遮挡的结构可按补写规则合理推断补画，补画内容在补写清单中按插图编号说明。redraw 模式下，relation 为 main／supporting 的 photo（未标 `simple_schematic:true`）记为 `skipped_photo`，原位输出 `[…（照片）：未重绘]` 占位，不再静默删除。
- 失败回退（自 0.7.0）：用户选择“重新绘制，失败或照片时保留原图”（确认选项 D）时传 `--image-fallback original`，重绘失败的图和上述照片在原位保留原图裁剪，块上记录 `fallback:{reason,source_sha256}`；回退前重新核对原图哈希，不一致则改为占位。原图裁剪按原样使用，不擦除其中的手写或水印像素。该选项只用于 redraw，重试不得改变。

## 理解与关联

完成原有主体筛选后，以同一份 `blocks` JSON 增加顶层 `figure_task`。文字／公式／表格保持原接口；插图暂用原始私有裁剪 PNG 的 image 块，并加入 `figure_id`。这是待处理数据，不可直接导出。

未获得 redraw 授权前只做区域检测、分类和正文关联，不进行详细结构理解、绘图或调用图像生成工具；plan 阶段的 figure 不需要 understanding／drawing。确认 redraw 后才补充以下示例中的理解与绘图字段。

- 用稳定 block id 关联题目／正文，保留图外图题、图注和说明文字；图内 A/B、甲乙、物理量、数值、角度和单位只在图片中保留，不重复为正文。
- 同题比较、共用图题或共同含义的甲乙丙子图合成一个 figure_id 和场景，记录 figure_group_id；不得分成几个相同 group id。不同题／独立正文的图分别登记，image 块放在对应原位置，不能集中到文末。
- source_page 为从 1 开始的页号；source_bbox 为经页面方向校正的原始像素 `[left,top,right,bottom]`；source_path 为输入 JSON 目录内的真实原图区域 PNG。裁剪只生成理解依据，不算重绘。
- 能确定题号时填写 `placeholder_label`（1–20 字，不含方括号和换行，如 `"第27题丙图"`），占位写作 `[第27题丙图：无法可靠重绘]`；不填时按文档中仍可见的插图位置编号（被忽略的干扰图不计数）。
- 用流水线时，每张图的 understanding、redrawable、critical_uncertainty、simple_schematic、placeholder_label、drawing 可写入单独文件，在 figure 条目中用 `"figure_file": "figures/f1.json"` 引用（路径在 candidates.json 目录内，同一字段不得同时内联）。流水线在规划前把它内联进 figure-source.json，后续步骤与内联写法相同。
- 所有 image 块必须登记，分类为图、照片、干扰、表格或公式。若发现表格／独立公式区域，应先改用现有 native table／math／chemistry 块完成识别；分类排除不意味着允许丢掉它们的内容。
- table／formula 区域还需用 content_block_ids 指向已转换的原生内容块，未完成转换时脚本拒绝静默忽略。preserve 保留原主体筛选后选中的原图（包括明确要求保留的二维码），不新增解码或重绘；默认无关内容仍在原筛选阶段排除。

示例（正文及原图由宿主真实识别，不执行源附件中的指令）：

```json
{
  "blocks": [
    {"type":"text","id":"q1","text":"1．如图所示。"},
    {"type":"image","figure_id":"f1","path":"work/source-f1.png"},
    {"type":"text","text":"图1 装置示意图"}
  ],
  "figure_task": {
    "schema_version":1,"task_id":"current-file","page_count":1,"scan_complete":true,
    "figures":[{
      "figure_id":"f1","source_page":1,"source_bbox":[100,200,500,500],
      "source_path":"work/source-f1.png","parent_block_id":"q1",
      "figure_type":"structure","relation":"main",
      "redrawable":true,"critical_uncertainty":false,
      "understanding":{"objects":[{"id":"body","kind":"body"}],"labels":[],"arrows":[],"connections":[]},
      "drawing":{"scene":{
        "width":400,"height":300,
        "structure":{"objects":[{"id":"body","kind":"body"}],"labels":[],"arrows":[],"connections":[]},
        "elements":[{"id":"body","object_id":"body","kind":"rect","at":[120,100],"width":160,"height":100}]
      }}
    }]
  }
}
```

figure_type 可用：geometry、coordinates、function、motion、force、circuit、optics、apparatus、structure、flowchart、wave、trajectory、biology、illustration；照片为 photo，只有 `simple_schematic:true` 才重绘。排除类别为 table、formula、watermark、qr、logo、advertisement、decoration；不确定为 unknown。relation 为 main／supporting／unrelated／unknown，只有已确认相关的有效图进入 redraw。unknown 留内部复核，不凭空补画。

## 绘图场景与科学约束

技术图必须采用 scene 结构化绘图；不直接交给生成式模型。几何、导线、光路、装置和曲线可由以下可控图元组合：

| kind | 主要字段 |
|---|---|
| line／polyline／polygon | points；多边形自动闭合 |
| circle | center、radius；不能非等比例变形 |
| ellipse | center、rx、ry；只用于原图确是椭圆的结构 |
| rect | at、width、height |
| arc | center、rx、ry、start、end；角度单位为度，画布 y 向下 |
| curve | 4 个 points，三次贝塞尔控制点；只能使用有原图依据的趋势／点位 |
| label | at（基线）、text 或 runs、size、anchor（start／middle／end） |

每个图元有唯一 id；主体图元的 object_id 对应 understanding.objects。线型可用 stroke_width、dash 和 arrow（none／start／end／both）；填充只能 none／black／white。禁止 arbitrary SVG、脚本、非等比例 transform、颜色、渐变和艺术纹理。

- canvas 宽高为 50–1200，默认 PNG 等比例放大 3 倍、300 dpi（画布过小时自动提高到最多 4 倍，以满足 PNG 不小于 200×150 像素；dpi 随倍数调整，物理尺寸不变），白底黑线；线宽至少 0.5 场景单位。单主体优先 400×300，内容不适合则调整画布；多主体横向或纵向布局依含义选择，不通过拉伸满足比例。
- labels 每项用 id、target 及 text／runs；对应 label 图元用 label_id 和相同 object_id。上下标用 `{"text":"R"}`、`{"text":"1","script":"sub"}`，上标为 sup，不转成可能歧义的 R1。图内化学标注按真实视觉排版，独立和正文化学仍沿用 LaTeX 源码规则。
- 标注字体（自 1.1.0，需求 25.1）：脚本用随包 STIX Two Text 衬线字体渲染，默认按教材惯例自动定体——纯字母的物理量符号、点名、线段名（R、P、AB、θ）斜体，数字、单位、含数字的文字、`+`、cm／sin 等多字母单位或函数名正体，中文用系统中文字体；化学式按 IUPAC 元素符号模式（Na、Cl、Fe、CO₂、H₂O、Ca(OH)₂）自动正体，而 `v₀t`、`R₁+R₂`、`AB₁` 等数学物理量保持斜体，O₂ 之类单字母化学式须显式标注。显式写法：图元或 run 加 `"style":"italic"` 或 `"upright"`（`{"text":"N","style":"upright"}` 表示单位牛）。style 只影响排版，不参与与 understanding.labels 的内容比对。字号比例与基线由脚本固定（下标 70%、下沉 25%，上标上抬 40%），不要手动缩小 run。
- understanding 是生成前的原图结构，不得为了让候选通过而修改。scene.structure 与其一致；objects、connections、labels、arrows 必须对应原图。
- connections 为主体 id 对，如 `["battery","resistor"]`，导线图元标相同 connection；arrows 每项记录 element_id、direction（候选画布方向向量），双向箭头另记 both:true。
- 几何自动检查可用 `geometry:[{"kind":"parallel","elements":["a","b"]}]`，同时支持 perpendicular、equal_length。相切、共线、交点、角度、中点、坐标刻度、曲线趋势、开关状态、电源极性、液面、仪器顺序等记入 facts 并逐项视觉检查；不宣称通用几何／科学证明。
- 组件、导线与节点（自 0.7.0）：电路图和常见实验装置优先用组件描述，由 `figure_components.py` 展开成上表图元后再走同样的校验和渲染。
  - 组件：`{"id":"L1","kind":"component","type":"lamp","object_id":"L1","at":[x,y],"orientation":"h","size":1,"params":{}}`。`at` 为组件中心（axes 为坐标原点），`size` 0.5–3。电路元件画法自 1.1.0 起按需求 19.1 的教材风格固定（电池长细正极／短粗负极、滑片实心向下箭头、空心转轴开关、正体电表字母、统一线宽），不得为模仿原图改用手写图元重画这些元件；滑动变阻器滑片端子 `p` 在电阻体上方 24 个单位，开关 `a` 端子在空心圆外侧。可用类型及参数用 `figure_components.py list` 查看：lamp、resistor、rheostat(slider)、battery(cells, positive, mark_positive)、switch(state, blade_side)、switch_spdt(to)、ammeter/voltmeter(subscript)、motor、meter_dial(ranges, major_ticks, minor_ticks, needle, needle_range, unit, terminals)、beaker(liquid)、test_tube(liquid, angle)、flask(liquid, stopper)、alcohol_lamp(lit)、iron_stand(clamp_y, ring_y)、thermometer(min, max, major, value, labels)、asbestos_net、axes(length, x_label, y_label, origin_label, x_ticks, y_ticks)。
  - 方向：电路元件可用 h、h-flip、v、v-flip；实验器材只能 h、h-flip；meter_dial 和 axes 只能 h，避免刻度或坐标反向。
  - understanding 中对应对象的 `kind` 若为组件类型，必须与 `type` 一致；对象可写 `params`（如 `{"state":"open"}`、`{"needle":1.6}`），与组件同名参数不一致时直接报错，用于自动核对开关状态、电源极性和读数。
  - 导线：`{"id":"w1","kind":"wire","from":"B1.b","to":"S1.a","route":"hv","via":[[x,y]]}`，端点可为“组件.端子”、节点 id 或 `[x,y]`；route 为 direct／hv／vh／manual。两端都是带 object_id 的组件或节点时自动生成 connection，否则必须写 connection。节点：`{"id":"j1","kind":"junction","at":[x,y],"object_id":"j1"}`。连接电路元件或节点的导线（含另一端为裸坐标点时）默认用元件线宽 1.0，节点默认半径 2；连接实验器材的导线仍为 1.5。电路导线只走横平竖直，via 点应与端子同行或同列，避免斜线。
  - 展开产生的子图元 id 为 `<组件id>/<部件>`，手写元素 id 不得含 `/`。组件内部固定文字（电表字母、表盘数字、坐标轴名称）和内部箭头带 `symbol:true`，不登记在 understanding.labels／arrows 中；题目自身的标注（L₁、S、甲、乙等）仍按 label 登记。
  - 画布自适配：scene 写 `"width":"auto","height":"auto","fit":{"margin":12}`，按内容外框平移并确定画布；写数值时视为上限，超出时报错并给出外框尺寸。
  - 预览：`python -X utf8 <skill-dir>/scripts/figure_components.py preview scene.json --output-dir work/preview` 只用于自查，产物不得作为复核输入。
- 已确认 circle／square 类型的主体有额外的圆形／等边防变形检查；已明确单调趋势可用 `curves:[{"element_id":"curve","trend":"increasing","x_direction":1,"y_direction":-1}]` 检查实际图元，其中方向对应画布坐标，trend 也可为 decreasing。极值和复杂分段仍必须视觉复核，不凭趋势生成原图不存在的曲线数据。
- 图元、标签或箭头越界会阻止绘图。中文字体优先使用系统中文字体；缺少可用字体时传 `--font`，不得以方框、乱码或删除标签代替。拉丁标注优先随包衬线字体（`assets/fonts/`），缺失时依次找系统 Times New Roman、Latin Modern、Liberation Serif，再回退无衬线字体：此时 `generate` 的 attempt 和 `review-template` 的行带 `font_fallback:true` 并附说明，复核状态只能填 minor_issue（填 pass 会被拒绝），最终 block.redraw 也保留该标记；不得静默忽略。传入 `--font` 时所有标注都用该字体（无斜体），不记降级。

一般不规则教材示意插画允许使用宿主已获准的图像生成能力。必须直接查看真实原图再生成，要求白底黑色、结构和标注准确、无艺术化效果。将真实生成 PNG 放到输入目录内，以 `drawing:{"generated_png":"work/generated-f1.png"}` 接入。脚本检查纯黑白、尺寸及其不等同原图；这不证明生成过程，必须视觉复核。宿主没有图像生成能力时，不假装已调用，按失败降级。技术图不能用此接口绕过结构化要求。

## 命令与状态

优先使用 SKILL.md 中的 `pipeline.py`，它按以下顺序调用同样的命令并管理文件名；以下为单独调用方式。

以下 source.json 已经过原主体筛选。输出 JSON 与其同目录；图像工作目录留在该目录内，相对路径保持可用。所有输出独占创建，不覆盖已有产物。

```text
python -X utf8 <skill-dir>/scripts/figure_workflow.py plan source.json --text-output text-reviewed.json
```

先用 text-reviewed.json 输出已完成的正文、公式和表格。依据 plan 结果执行一次确认；没有有效图不询问。已提前授权可传 `--image-mode redraw`；明确不要图片传 ignore；明确原图传 preserve。

```text
python -X utf8 <skill-dir>/scripts/figure_workflow.py generate source.json --image-mode redraw [--image-fallback original] --output-dir images --ledger work/attempt1.json
```

记录 detected、classified、understood、redrawable、generated、validated、needs_retry、failed 等状态。结构化生成同时得到 SVG 和 PNG，生成式得到 PNG。生成成功只表示 awaiting_validation，不等于可交付。首次（attempt 1）结构化绘图因越界、结构校验等渲染失败时，进入 `needs_retry`（附 `render_errors`），允许修正一次 `drawing`；前提不满足（`critical_uncertainty:true`、`redrawable:false` 或技术图误用 `generated_png`）或第 2 次仍失败则直接记为 `failed`。

## 真实原图对照与有限重试

优先使用 `pipeline.py review`／`retry`；以下为单独调用方式。`generate` 可加 `--review-template <文件>` 输出已预填哈希的复核模板（流水线自动生成）。模板中所有判断为 null，必须逐项看图后填写；未填写或照抄的复核会被拒绝。`view_files` 只指示要查看的文件，不代表已经查看。

宿主必须查看原图区域、原图结构理解、实际生成 PNG，并检查 SVG 的结构／标注。逐项比较主体数量、连接、标注及上下标、箭头、相对位置、几何、坐标、黑白、遗漏、无关元素和科学含义。不可仅复制源理解或信任生成模型自述。

在 reviews.json 中保存 `reviews` 数组，每项含 figure_id、attempt、source_sha256、png_sha256（有 SVG 还含 svg_sha256）、reviewed_by:"host_vision"、status、notes 数组和 checks。哈希取生成 ledger 的对应文件记录并核对实际文件，不能填任意值。

checks 必须逐项给出真实布尔判断：subject_count、connections、labels、arrow_directions、relative_positions、geometry、coordinates、black_white、completeness、no_unrelated_elements、scientific_meaning。某项不适用且不会引起错误时可为 true，notes 说明理由。

- pass：全部关键项通过。
- minor_issue：只有不影响含义的外观问题，关键项仍全部通过；可接受或修正。
- major_issue：关键结构或标注错误，自动修正一次；不得把关键失败降为 minor_issue。
- unreliable：原图／结果无法可靠比较，直接降级。

```text
python -X utf8 <skill-dir>/scripts/figure_workflow.py complete source.json --ledger work/attempt1.json --reviews work/reviews1.json --next-ledger work/reviewed1.json --output figures-reviewed.json
```

pending_reviews 或 needs_retry 非空时，不产生最终 figures-reviewed.json。首次 `major_issue` 或结构化绘图 `render_error`：只修改对应 figure 的 `drawing`，保持原始 `understanding`、来源、关联和全部正文不变；随后自动执行：

```text
python -X utf8 <skill-dir>/scripts/figure_workflow.py generate source.json --image-mode redraw --output-dir images --previous work/reviewed1.json --ledger work/attempt2.json
```

查看第二次实际产物后再次 complete（使用 reviews2.json、reviewed2.json）。每图最多两次生成；第二次仍失败或结构不可确定时，在对应原位输出 `[第1张插图：无法可靠重绘]`（有 placeholder_label 时用它，否则按仍可见的插图位置编号；内部 figure_id 记录在 figure_processing.failed_figures）；选择了 `--image-fallback original` 时改为保留原图裁剪并记录在 fallback_figures。其他文字和通过的图继续交付。流水线中重试用 `pipeline.py retry --drawing <figure_id>=<文件>` 只提交被要求修改的图。不得无限重试，不把失败或未复核图片当成正确图输出。

## 最终输出

完成后的 figures-reviewed.json 可交给原 export_page.py／export_docx.py；未完成 figure_task 会被导出器拒绝。文件模式 HTML 内嵌 PNG，Markdown 原位引用 SVG（无 SVG 时 PNG），figures/ 同时携带兼容位图和矢量；聊天展示用宿主真实附件或绝对路径。Word 嵌入等比例 PNG，重绘图居中且不超过正文区域，保持原有题干／选项分页关联。

Word 是否需要输出继续按 pdf-word.md 的独立选择执行。已明确要 Word 不再询问；图片选择“是”不授权 Word。SVG 仍为可编辑矢量文件，Word 嵌入 PNG 不宣称为 Word 原生绘图对象。内部 ledger、源码理解、哈希及失败报告不混入学生正文，只有实际无法重绘位置需简短说明。

## V1.1 专项增量规则（图组分区、实物器材、专项校验与局部返修）

### 原图保真与科学性优先级

1. 清晰可辨且与作答有关的源图数据、关系、选项现象、故意错误接线或错误操作必须原样保留，不得以科学正确性为由替学生纠正。
2. 利用题干和同组子图辅助理解模糊原图；当可辨印刷内容与题干存在影响作答的真实冲突时，记录证据与冲突，按关键不确定项进入复核或回退，不擅自选定一方。
3. 器材外观、非关键透视、非考查性瞬时位置可在不改变原题含义的前提下按初中教材合理重建，不得新增解题线索（答案、读数提示、额外受力箭头、电荷或冲程名等）。
4. 关键值、端子接线、状态或方向经放大与题干对照仍不可辨时，直接进入复核或回退，不得凭常识推断唯一答案。
5. 独立重绘时题干仅作理解依据，不把题干或独立文字选项绘入图片；A–D 顺序、编号及与图一体的选项文字一同保留。默认排除手写叉号、勾画、改线弧线及扫描杂质；无法确认某段线是否印刷且影响作答时进入关键待复核。

### 生成前事实记录扩展

`understanding` 在原有 `objects`/`labels`/`arrows`/`connections`/`facts`/`geometry`/`curves` 基础上，可记录以下生成前事实字段（非绘图溯源字段无需在 `scene.structure` 中重复）：

- `fact_version`（整数，默认 1）、`fact_changes`（事实纠正变更记录）、`stem_context`（题干语境）、`evidence`（原图可见特征／题干互证依据）、`design_allowances`（可清理／可简化／可重排项）、`uncertainties`（区分 `critical` 与 `appearance`）、`verification_targets`（易错核对清单）。
- 禁止为迁就候选结果而篡改原图事实；原事实确有识别错误时，须通过新版本事实纠正记录新依据后重新理解与复核。

### 图组／子图两级处理、混合路由与跨宿主降级

- **图组**（`figure`）仍是文档插入、排序与交付单位；**子图/分区**（`subfigures` 数组，每项含组内唯一 `subfigure_id`、`label`、`figure_type`、`source_bbox`、`understanding`、`drawing`）是事实理解、路由、复核、重试（每分区最多 2 次，已通过分区不重生成）与局部返修的最小单位。旧版单图输入（无 `subfigures`）保持完全兼容。
- **分区路由**：技术类子图（电路、仪表、坐标、几何、装置、结构、运动/受力等）必须走结构化 `scene`；仅 `illustration` 或标记 `allow_generative:true` 的教学现象照片可接入宿主图像生成能力（`generated_png`），不得为图省事把含技术子图的整个图组送入生成式模型。
- **跨宿主降级**：不绑定特定 AI 平台或在线生图服务。宿主无图像生成工具时，可将可结构化表达的插画降为 `scene` 示意，或在 `drawing` 中显式写 `{"tool_unavailable":true}` 按策略降级为占位或授权原图，不阻断文字、表格、公式及其他插图。
- **依赖与回退**：
  - 独立子图失败只回退该分区（图组内生成清晰黑白占位或授权原图裁剪），保留已通过子图并合成完整图组。
  - 共享 `dependency_group` 的子图任一失败时同组一起回退；标记 `strong_dependency:true` 或图组 `group_dependency:"strong"` 时任一失败则整组回退。
  - 关键不确定（`critical_uncertainty:true`）或 `redrawable:false` 直接进入回退，不强制消耗生成次数。
  - 传入 `--disallow-handwriting-fallback`（或图/子图标 `disallow_handwriting_fallback:true`）且原区域含手写（`has_handwriting:true`）时，除非明确标记 `allow_handwriting_original_exception:true`，失败回退改用占位而不嵌入带手写原图。
- **合成与双层复核**：全部子图通过后按 `layout`（`horizontal`/`vertical`/`grid`、`cols`、`gap`、`padding`、`caption_position`）合成图组 PNG（全结构化无回退时同步合成合规 SVG；混合图组以完整 PNG 为正式产物并在台账保留 `subfigure_svgs`），再经图组级复核确认全局对应后交付。

### 实物器材组件与三项专项校验

`figure_components.py`（模板版本 `1.3.0`）新增初中物理高频实物器材与数据空间绘图能力：

- **实物电学组件**：`phys_meter`（指针式 A/V 表，未给 `ranges` 时不编造量程数字）、`phys_knife_switch`（闸刀开关，底座轮廓不横跨端子）、`phys_rheostat`（滑动变阻器，含瓷筒绕线、滑杆、滑片 P、A/B/C/D 端子）、`phys_rotary_rheostat`（旋钮式变阻器，A/C 接电阻丝两端、B 接滑片轴心，暴露 `knob`/`wiper`/`wire` 引线锚点）、`phys_lamp_holder`（小灯座）、`phys_battery`（圆柱干电池/电池盒，串联极性可追踪）、`phys_resistor`（实验用电阻件）、`binding_post`（独立接线柱）。
- **实验与量值组件**：`clinical_thermometer`（35–42 ℃ 体温计，0.1 ℃ 分度，数据空间精确液柱，不印答案）；`alcohol_lamp` 新增可选 `liquid`/`inner_flame`/`base`；`iron_stand` 新增可选 `clamp2_y`；`axes` 新增 `x_range`/`y_range`/`x_major`/`y_major`/`x_minor`/`y_minor`/`grid` 数据空间映射，配合 `kind:"data_curve"` 按数据坐标直接生成精确折线。
- **三项机器专项校验**（在 `expand_scene` 展开并平移画布后针对真实图元几何执行）：
  1. `understanding.terminal_connections`：逐端子校验每根导线的实际起止坐标是否到达目标锚点，拦截接错邻端、悬空虚接、额外跨接及误触无关端子；区分同端共接与跨线无连接。
  2. `understanding.data_space`：校验 `key_points`（曲线经过精确数据点）、`coincident_segments`（如沸腾平台重合段）及 `readings`（体温计/温度计实际渲染液柱端点与电表实际指针角度）。
  3. `understanding.state_checks`：校验 `relative_position`（如棒在气球左侧且保留最小间隙 `min_gap`）及 `monotonic_radius`（如沸腾气泡上升变大/变小）。

### 交付后局部返修与打印可读性

- **局部返修**：对已完成运行执行 `pipeline.py repair --state <state> --run-id <新run-id> --target <fid[:subid]> --drawing <target>=<文件> [--fact-correction <文件>] --output <新输出>`。未修改分区直接复用原渲染产物（不重生成），重新合成时自动执行 `verify_unchanged_regions` 验证未修改分区像素完全一致；被修改分区在新任务版本中重新获得最多 2 次生成预算。外观返修锁定原 `understanding`；事实纠正须提供 `reason`、`evidence` 与 `updates` 并递增 `fact_version`。
- **打印可读性基准**：单图按约 80 mm、多子图按约 150 mm 等效打印宽度核验数字/文字/上下标、刻度、端子连线及白底黑线清晰度；可用 `figure_drawing.check_print_readability` 辅助检查标注字高与重叠，但不替代真实原图与 Word 嵌入视觉核验。

