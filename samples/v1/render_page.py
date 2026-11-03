"""Draw a synthetic printed exam page (PIL) from the sample content.

The page carries what V1.0 must cope with: printed body with sub/superscripts,
stacked fractions and reaction conditions, a printed answer section, blue handwriting,
a promotional watermark, a header, and (for M06) an ink blot over one digit.
Every block's bounding box is recorded so candidates can cite source spans.
"""
import math
import random
import re
from PIL import Image, ImageDraw, ImageFilter, ImageFont

CJK = '/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc'
SANS = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
SYMBOLS = {'triangle': '△', 'angle': '∠', 'perp': '⊥', 'Omega': 'Ω', 'in': '∈', 'geq': '≥', 'leq': '≤',
           'cdot': '·', 'times': '×', 'Delta': '△', 'uparrow': '↑', 'downarrow': '↓', 'rightarrow': '→',
           'alpha': 'α', 'pi': 'π'}
WIDTH, HEIGHT, MARGIN = 1240, 1754, 90


def font(size, sans=False):
    return ImageFont.truetype(SANS if sans else CJK, size)


class Box:
    def __init__(self, width, ascent, descent, paint):
        self.width, self.ascent, self.descent, self.paint = width, ascent, descent, paint


def text_box(text, size, italic=False):
    f = font(size)
    width = f.getlength(text)
    return Box(width, size * 0.88, size * 0.25,
               lambda d, x, y: d.text((x, y - size * 0.88), text, font=f, fill=(25, 25, 25)))


def hbox(boxes):
    width = sum(b.width for b in boxes)
    ascent = max((b.ascent for b in boxes), default=0)
    descent = max((b.descent for b in boxes), default=0)

    def paint(d, x, y):
        for b in boxes:
            b.paint(d, x, y)
            x += b.width
    return Box(width, ascent, descent, paint)


def shifted(box, dy):
    return Box(box.width, max(0, box.ascent - dy), max(0, box.descent + dy), lambda d, x, y: box.paint(d, x, y + dy))


def parse(latex, size):
    """Tiny LaTeX layout: groups, _ ^, \\frac, \\sqrt, \\xrightarrow, \\mathrm/\\mathbf/\\text, symbols."""
    pos = 0

    def group():
        nonlocal pos
        if pos < len(latex) and latex[pos] == '{':
            depth, start = 1, pos + 1
            pos += 1
            while depth:
                depth += {'{': 1, '}': -1}.get(latex[pos], 0)
                pos += 1
            return latex[start:pos - 1]
        if latex[pos] == '\\':
            match = re.match(r'\\[A-Za-z]+', latex[pos:])
            pos += len(match[0])
            return match[0]
        pos += 1
        return latex[pos - 1]

    def optional():
        nonlocal pos
        if pos < len(latex) and latex[pos] == '[':
            end = latex.index(']', pos)
            value = latex[pos + 1:end]
            pos = end + 1
            return value
        return ''

    boxes = []
    while pos < len(latex):
        char = latex[pos]
        if char in '_^':
            pos += 1
            script = parse(group(), int(size * 0.62))
            base = boxes.pop() if boxes else text_box('', size)
            if char == '_':
                boxes.append(hbox([base, shifted(script, size * 0.28)]))
            else:
                boxes.append(hbox([base, shifted(script, -size * 0.42)]))
            continue
        if char == '{':
            boxes.append(parse(group(), size))
            continue
        if char == '\\':
            match = re.match(r'\\([A-Za-z]+|.)', latex[pos:])
            name = match[1]
            pos += len(match[0])
            if name in {'mathrm', 'mathbf', 'text', 'operatorname'}:
                boxes.append(parse(group(), size))
            elif name == 'frac':
                top, bottom = parse(group(), int(size * 0.8)), parse(group(), int(size * 0.8))
                width = max(top.width, bottom.width) + 6

                def paint(d, x, y, top=top, bottom=bottom, width=width):
                    bar = y - size * 0.32
                    top.paint(d, x + (width - top.width) / 2, bar - top.descent - 3)
                    d.line((x, bar, x + width, bar), fill=(25, 25, 25), width=2)
                    bottom.paint(d, x + (width - bottom.width) / 2, bar + bottom.ascent + 3)
                boxes.append(Box(width, size * 0.32 + top.ascent + top.descent + 3,
                                 bottom.ascent + bottom.descent + 3 - size * 0.32, paint))
            elif name == 'sqrt':
                inner = parse(group(), size)
                radical = text_box('√', size)

                def paint(d, x, y, inner=inner, radical=radical):
                    radical.paint(d, x, y)
                    d.line((x + radical.width - 2, y - inner.ascent - 2, x + radical.width + inner.width, y - inner.ascent - 2),
                           fill=(25, 25, 25), width=2)
                    inner.paint(d, x + radical.width, y)
                boxes.append(Box(radical.width + inner.width, inner.ascent + 4, inner.descent, paint))
            elif name == 'xrightarrow':
                below = parse(optional(), int(size * 0.6))
                above = parse(group(), int(size * 0.6))
                width = max(above.width, below.width) + 24

                def paint(d, x, y, above=above, below=below, width=width):
                    mid = y - size * 0.3
                    d.line((x + 2, mid, x + width - 2, mid), fill=(25, 25, 25), width=2)
                    d.polygon([(x + width - 2, mid), (x + width - 12, mid - 5), (x + width - 12, mid + 5)], fill=(25, 25, 25))
                    above.paint(d, x + (width - above.width) / 2, mid - 6)
                    below.paint(d, x + (width - below.width) / 2, mid + below.ascent + 4)
                boxes.append(Box(width, size, size * 0.6, paint))
            elif name in SYMBOLS:
                boxes.append(text_box(SYMBOLS[name], size))
            elif name == ',':
                boxes.append(text_box(' ', size // 2))
            else:
                boxes.append(text_box(name, size))
            continue
        if char == ' ':
            pos += 1
            continue
        pos += 1
        boxes.append(text_box('−' if char == '-' else char, size))
    return hbox(boxes)


def line_boxes(text, size):
    """Paragraph markup ($math$, @chem@) to a list of boxes split for wrapping."""
    from content import runs
    boxes = []
    for run in runs(text):
        if run['type'] == 'text':
            # 〔x〕 marks a transcription inference: the page prints x and is later blotted.
            for chunk in re.split(r'(〔[^〕]*〕)', run['text']):
                if chunk.startswith('〔'):
                    box = text_box(chunk[1:-1], size)
                    box.mark = True
                    boxes.append(box)
                    continue
                for piece in re.findall(r'[A-Za-z0-9\'".,!?:;-]+\s*|\s+|.', chunk):
                    boxes.append(text_box(piece, size))
        else:
            boxes.append(parse(run['latex'], size))
    return boxes


class Page:
    def __init__(self):
        self.image = Image.new('RGB', (WIDTH, HEIGHT), (250, 249, 245))
        self.draw = ImageDraw.Draw(self.image)
        self.y = MARGIN
        self.marks = []

    def paragraph(self, text, size=30, indent=0, gap=14):
        boxes = line_boxes(text, size)
        top, x = self.y, MARGIN + indent
        line, lines = [], []
        for box in boxes:
            if x + box.width > WIDTH - MARGIN and line:
                lines.append(line)
                line, x = [], MARGIN + indent
            line.append(box)
            x += box.width
        lines.append(line)
        for line in lines:
            ascent = max(b.ascent for b in line)
            descent = max(b.descent for b in line)
            baseline = self.y + ascent
            x = MARGIN + indent
            for box in line:
                box.paint(self.draw, x, baseline)
                if getattr(box, 'mark', False):
                    self.marks.append((x, baseline - box.ascent, x + box.width, baseline + box.descent))
                x += box.width
            self.y = baseline + descent + 10
        self.y += gap
        return [MARGIN, int(top), WIDTH - MARGIN, int(self.y)]

    def figure(self, png_path, width=420):
        figure = Image.open(png_path).convert('L')
        figure = figure.resize((width, int(figure.height * width / figure.width)))
        # Print-like grey ink with paper noise.
        ink = Image.eval(figure, lambda v: 60 if v < 128 else 250).convert('RGB')
        left = (WIDTH - width) // 2
        self.image.paste(ink, (left, int(self.y)))
        box = [left, int(self.y), left + width, int(self.y + ink.height)]
        self.y += ink.height + 20
        return box

    def handwriting(self, xy, text, size=34):
        f = ImageFont.truetype(SANS, size)
        self.draw.text(xy, text, font=f, fill=(30, 60, 200))

    def tick(self, x, y):
        self.draw.line((x, y, x + 14, y + 16, x + 40, y - 18), fill=(30, 60, 200), width=4)

    def watermark(self, text):
        layer = Image.new('RGBA', self.image.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        f = font(64, sans=True)
        for row in range(3):
            d.text((160, 520 + row * 420), text, font=f, fill=(150, 150, 150, 70))
        layer = layer.rotate(18, center=(WIDTH / 2, HEIGHT / 2))
        self.image = Image.alpha_composite(self.image.convert('RGBA'), layer).convert('RGB')
        self.draw = ImageDraw.Draw(self.image)

    def blot(self, box):
        x0, y0, x1, y1 = box
        self.draw.ellipse((x0, y0, x1, y1), fill=(40, 40, 60))

    def save(self, path, seed=7):
        random.seed(seed)
        pixels = self.image.load()
        for _ in range(4000):
            x, y = random.randrange(WIDTH), random.randrange(HEIGHT)
            pixels[x, y] = (200, 200, 195)
        self.image.filter(ImageFilter.GaussianBlur(0.4)).save(path)

