# 0.4.0 需求核对与冲突处理

依据用户引用的“规范化功能需求”会话中最新《页面主体内容识别、无关元素过滤与规则冲突治理需求说明书》实施。基线：main 的 416c8f3（0.3.1）。本文件为开发审查记录；运行时规则唯一来源是 [main-content.md](../plugins/image-print-extractor/skills/image-print-extractor/references/main-content.md)。

## 开发前审查

| 新增／现有规则 | 基线实际规则 | 冲突／缺口 | 处理及文件 |
|---|---|---|---|
| 默认主体印刷体 | README 所有印刷内容；SKILL 有过滤例外 | 口径歧义 | 替换为主体及支持内容；README、SKILL |
| 页眉页脚语义判断 | SKILL 笼统排除页眉页脚；示例又保留章节标题 | 边界冲突 | 删除笼统排除；main-content、examples |
| 无法识别用 XXX | SKILL 允许结合上下文、语法恢复 | 猜补风险 | 替换旧恢复规则，仅可见笔画／结构；SKILL、pdf-word |
| 通用 Markdown／表格专项 | 真实 HTML 表格、Word 原生表格；Markdown 原位链接 | 无冲突 | 保留接口，新增筛选后的集成测试 |
| 不新增内容／二维码占位 | 缺少二维码用途区分 | 缺口 | 正文二维码可占位；宣传二维码不占位，不默认解码 |
| 保留图中文字／过滤图片 | PNG 保留印刷线条标签；无 Logo 研究对象规则 | 缺口 | 按关联判别；图内标签、图号、实验说明受保护 |
| 手写／全部文字 | 默认忽略全部手写；范围覆盖仅概括说明 | 歧义 | 全部文字默认全部印刷；明确包括手写才包含；指定范围独立 |
| 用户当前指令／默认过滤 | 当前请求优先但无明确模式 | 缺口 | main、body、all-printed、all-text、preserve 参数来自聊天 |
| 水印／覆盖区正文 | 有去水印及可靠恢复要求 | 缺少明确重叠保护 | 水印与正文分元素；不删矩形、不改像素；嵌套主体保护 |
| 忠实原文／LaTeX | 数学 OMML，化学源码，不解题／配平 | 无冲突；需求化学示例用美元分隔符与现有源码默认不同 | 保留原插件默认化学源码；只有用户要求渲染才用数学分隔符 |
| 多文件规则版本 | SKILL、PDF 参考、README 分别维护过滤 | 重复维护风险 | main-content 为唯一判断来源，其余链接并仅保留专项流程 |

上述方案先核对后实施，无独立 OCR 引擎、像素去水印、固定位置裁切、关键词黑名单或无关架构重建。PDF 准备与裁剪保持原有逻辑；实际验收发现的 Word 分页、摄氏度空距及短单位拆行已在导出器和数学转换器中修复，并新增回归测试。

## 需求映射

| 说明书章节 | 实现及验证 |
|---|---|
| 1–6 背景、目标、术语、流程 | SKILL 前置筛选；main-content 主体与支持内容定义 |
| 7–14 广告、联系方式、品牌、水印、二维码、页眉、横幅、Logo、装饰、插图 | main-content 元素作用判断；18 场景、重叠及二维码测试 |
| 15–21 手写、印刷答案、数学、物理、化学、表格、双栏 | 范围参数；原33项回归；新导出集成、顺序及空白保护 |
| 22–23 可见结构恢复、XXX、形式规范化 | 替换猜补规则；原公式结构/XXX测试，新混排保真测试 |
| 24–25 用户覆盖、优先级 | scope、preserve、include-handwriting；元数据不能改变用户范围 |
| 26–31 增量关系、冲突、禁止实现、类别、主体判断、误删控制 | 保守 decision；UNKNOWN 保留；冲突复核；父级不得吞掉主体子项 |
| 32–33 输出与异常 | 内部 selection.review.json 不混入正文；继承实际缺项提示 |
| 34–40 典型场景 | 18 已标注测试候选及用户两张实图本地核对 |
| 41–47 开发审查、单一来源、旧规则替换、模块建议 | 本审查记录；只有必要文件改动；筛选脚本接入原导出流程 |
| 48–51 新功能与回归验收 | tests/test_main_content.py、原测试、包验证；边界见测试报告 |
| 52–54 分阶段与完成报告 | 先审查，后实现；更新记录、报告、可复核补丁和包 |
| 55–56 非目标、统一行为 | 不修改源图像素；不猜补、不解题、不摘要、不默认解码 |

## 修改文件与用途

- SKILL.md：路由主体筛选，替换猜补及笼统过滤规则。
- references/main-content.md：范围、优先级、元素判断、覆盖保护、二维码和筛选接口。
- references/examples.md、pdf-word.md、rich-output.md：边界示例、PDF逐页筛选与导出步骤同步。
- scripts/select_content.py：执行宿主语义分类，保留顺序／表格／源码，记录审计报告。
- scripts/content_blocks.py、export_page.py、export_docx.py：拒绝未筛选的带 selection 候选，旧 reviewed JSON 继续兼容。
- plugin.json、.codex-plugin/plugin.json、agents/openai.yaml：同步0.4.0及功能发现文案；图标与Logo保持原文件。
- tests/test_main_content.py、fixtures/main-content.json：范围、保守筛选、保护与导出回归。
- README、CHANGELOG、docs：统一公开说明与验证边界。
- references/formulas.md：移除重复段落及遗留猜补表述，明确可见结构恢复；scripts/formulas.py 修复空基底度符号及短单位拆行。
- tests/test_pdf_word.py、test_formulas.py：新增分页关联、显式覆盖、摄氏度与短单位的回归；tests/generate_visual_cases.py 提供可复现的受控图像。

## 兼容性与限制

既有 blocks、runs、math、chemistry、table、image 类型不变。无 selection 的已复核输入维持原导出行为；存在 selection 的候选必须先筛选，防止未经处理的广告直接进入导出。筛选结果写在源 JSON 同目录，不破坏相对 PNG 路径。正文优先于过滤；明确手写仍默认排除，不确定印刷／手写则保留复核。

语义准确性仍依赖宿主模型和原图。像素中仍可能存在图内水印，脚本不擦除；不能可靠恢复时应报告图像缺项。正文二维码只保留图像／占位，不新增解码器。测试不代表所有图像、Word版本或宿主新会话都稳定通过。
