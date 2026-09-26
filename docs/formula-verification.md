# 0.3.0 表达式导出验证记录

验证日期：2026-09-26。验证对象是 `tests/fixtures/formulas.json` 中的合成样例，不代表真实扫描识别准确率。

- 28 项自动化测试通过，覆盖原有导出功能、数学二维结构、函数/单位正斜体、行内/独立及表格混排、化学源码保留、异常占位和定位记录。
- 仓库包检查、插件清单验证、技能验证通过。
- Microsoft Word 成功打开样例并识别 12 个原生公式，另存后仍保留 12 个公式及分式、根式、上下标、矩阵、向量重音和横线结构，普通文字中的化学源码保持不变。
- 通过 Word 对象模型将测试文档复制到新文档，在第一个上下标公式中将底数改为 `z`，保存后仍有 12 个原生公式。
- Word 导出一页 PDF 并检查页面图像，已复核混排、伸缩括号、向量箭头、函数间距、分段函数、矩阵和表格，无可见重叠或裁切。

自动测试命令见 README。样例生成命令：

```sh
python plugins/image-print-extractor/skills/image-print-extractor/scripts/export_docx.py tests/fixtures/formulas.json --output work/formula-sample.docx --word-confirmed
```

真实扫描、其他 Word 版本以及目标打印环境仍应按 [验收清单](acceptance.md) 复核。支持范围限于插件明确声明的 LaTeX 子集；不支持的表达式进入复核流程，不能据此宣称完整 LaTeX 支持。
