"""Crop pixels only; this does not remove handwriting or perform OCR."""
import argparse
from pathlib import Path
from PIL import Image, ImageOps


def crop(source, target, box):
    source, target = Path(source), Path(target)
    if target.suffix.lower() != '.png':
        raise ValueError('Output must be PNG')
    if target.exists():
        raise FileExistsError(target)
    with Image.open(source) as raw:
        im = ImageOps.exif_transpose(raw)
        left, top, right, bottom = box
        if not (0 <= left < right <= im.width and 0 <= top < bottom <= im.height):
            raise ValueError('Crop box must be inside the oriented image')
        target.parent.mkdir(parents=True, exist_ok=True)
        im.crop(box).save(target, format='PNG')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('target')
    parser.add_argument('--box', nargs=4, type=int, required=True)
    args = parser.parse_args()
    crop(args.source, args.target, tuple(args.box))
