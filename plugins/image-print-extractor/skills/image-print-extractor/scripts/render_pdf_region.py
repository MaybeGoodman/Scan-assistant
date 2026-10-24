"""Re-render one PDF page region at a higher DPI for closer reading; no OCR, never a deliverable figure."""
import argparse
from pathlib import Path
import pypdfium2 as pdfium
from prepare_pdf import MIN_DPI, check_dpi

MAX_REGION_DPI = 600


def render_region(source, page, box, base_dpi, dpi, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    if target.suffix.lower() != '.png':
        raise ValueError('Output must be PNG')
    if target.exists():
        raise FileExistsError(target)
    check_dpi(base_dpi, MIN_DPI, MAX_REGION_DPI)
    check_dpi(dpi, MIN_DPI, MAX_REGION_DPI)
    if dpi < base_dpi:
        raise ValueError('--dpi must be greater than or equal to --base-dpi')
    if len(box) != 4 or any(type(v) is not int for v in box):
        raise ValueError('Box must contain four integer pixel coordinates')
    left, top, right, bottom = box
    if not (0 <= left < right and 0 <= top < bottom):
        raise ValueError('Box must have positive area')
    ratio = dpi / base_dpi
    scaled = (round(left * ratio), round(top * ratio), round(right * ratio), round(bottom * ratio))
    with pdfium.PdfDocument(source) as pdf:
        if type(page) is not int or not 1 <= page <= len(pdf):
            raise ValueError(f'页码无效：{page}（总页数 {len(pdf)}）')
        item = pdf[page - 1]
        try:
            bitmap = item.render(scale=dpi / 72)
            try:
                image = bitmap.to_pil()
            finally:
                bitmap.close()
        finally:
            item.close()
    if scaled[2] > image.width or scaled[3] > image.height:
        raise ValueError('Box is outside the rendered page')
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        image.crop(scaled).save(stream, format='PNG')
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('--page', type=int, required=True, help='1-based page number in the original PDF')
    parser.add_argument('--box', nargs=4, type=int, required=True, metavar=('L', 'T', 'R', 'B'),
                        help='Pixel box on the page image rendered at --base-dpi')
    parser.add_argument('--base-dpi', type=int, required=True)
    parser.add_argument('--dpi', type=int, required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(render_region(args.source, args.page, tuple(args.box), args.base_dpi, args.dpi, args.output))


if __name__ == '__main__':
    main()
