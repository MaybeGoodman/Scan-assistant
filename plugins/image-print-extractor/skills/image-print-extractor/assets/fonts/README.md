# 随包字体

- `STIXTwoText-Regular.ttf`、`STIXTwoText-Italic.ttf`：STIX Two Text，来源 https://github.com/stipub/stixfonts（`source/STIXTwoText-*.input.ttf`，提交 bea1dc9，2026-03），SIL Open Font License 1.1，许可全文见 `OFL.txt`。
- 用途：结构化重绘中标注文字的默认衬线字体（需求第 25.1 节）；拉丁物理量符号用 Italic，数字、单位和电表字母用 Regular。中文仍使用系统中文字体。
- 插件不会自动下载或安装字体；缺少这两个文件时按 `figure_drawing.py` 中的系统衬线字体链查找，再回退无衬线字体并标记 `font_fallback`。
