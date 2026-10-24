"""Parse the user's single reply to the combined pre-start confirmation.

Two independent choices may be asked in one message: Word output (PDF only) and image
handling. Each is decided only by the part of the reply that answers it; generic replies
such as "好的" to a two-part question stay ambiguous. Input is the current chat reply only.
"""
import argparse
import json
import re
import sys
import unicodedata
from figure_workflow import reply_mode

ITEMS = ('word', 'image')
SEPARATORS = re.compile(r'[，,、；;。！!？?\s~～…]+')
NUMBERED = re.compile(r'([1-9])\s*[-.:：、．)）]?\s*([a-z])')
LETTER_ONLY = re.compile(r'^\s*([a-z])\s*$')
WORD_LETTERS = {'a': True, 'b': False}
# 'redraw:original' = redraw, and keep the original crop where a figure fails or is a photo.
IMAGE_LETTERS = {'a': 'redraw', 'b': 'ignore', 'c': 'preserve', 'd': 'redraw:original'}
WORD_KEYS = ('word', 'docx', '文档')
WORD_NO_OUTPUT = ('直接输出', '只要提取内容', '只输出内容', '不生成文档')
IMAGE_KEYS = ('图', '画', '绘', '插图')
NEGATIONS = ('不要', '不用', '不需要', '无需', '不生成', '别', '不画', '不重绘', '忽略', '跳过', '不')
PRESERVE_KEYS = ('保留原图', '原图保留', '用原图', '原图即可', '保留图片原样')
REDRAW_KEYS = ('重绘', '重新绘制', '重画', '画出来', '画一下', '也要', '要图', '图也生成', '图片也处理', '绘制')
GENERIC = {'是', '否', '好', '行', '对', '嗯', '可以', '可', '要', '不', '不要', '不行', '不是', '没问题', '需要',
           '不需要', '不用', '继续', '算了', '没必要', '好的', '是的', '可以的', '行的', '好吧', '嗯嗯', '都行',
           'ok', 'okay', 'yes', 'no', 'y', 'n'}
WORD_YES = {'是', '是的', '好', '好的', '可以', '可以的', '行', '对', '要', '需要', '需要的', '没问题', '嗯',
            'ok', 'okay', 'yes', 'y', '生成', '要的'}
WORD_NO = {'否', '不', '不要', '不用', '不需要', '不行', '不是', '算了', '没必要', 'no', 'n'}
# Option labels shown by multiple-choice tools.
WORD_LABELS = {'生成word(.docx)': True, '生成word': True, '直接输出提取内容': False}
IMAGE_LABELS = {'重新绘制插图': 'redraw', '重新绘制': 'redraw', '不要图片': 'ignore', '保留原图': 'preserve',
                '重新绘制插图(失败处留占位)': 'redraw'}


def normalize(text):
    return unicodedata.normalize('NFKC', text).strip().lower()


def compact(text):
    return re.sub(r'\s+', '', text)


def word_value(fragment):
    if compact(fragment) in WORD_LABELS:
        return WORD_LABELS[compact(fragment)]
    if any(key in fragment for key in WORD_NO_OUTPUT):
        return False
    if any(key in fragment for key in WORD_KEYS):
        return False if any(neg in fragment for neg in NEGATIONS) else True
    return None


def fallback_fragment(fragment):
    """'失败时保留原图' or '照片保留原图' qualifies a redraw answer instead of meaning preserve."""
    return '原图' in fragment and ('失败' in fragment or '照片' in fragment)


def image_value(fragment):
    if compact(fragment) in IMAGE_LABELS:
        return IMAGE_LABELS[compact(fragment)]
    if fallback_fragment(fragment) or (any(key in fragment for key in PRESERVE_KEYS)
                                       and any(key in fragment for key in REDRAW_KEYS)):
        return 'redraw:original'
    if any(key in fragment for key in PRESERVE_KEYS):
        return 'preserve'
    try:
        mode = reply_mode(fragment)
        if fragment not in GENERIC:
            return mode
    except ValueError:
        pass
    if not any(key in fragment for key in IMAGE_KEYS) and fragment not in {'只要文字', '跳过'}:
        return None
    if any(neg in fragment for neg in NEGATIONS) or fragment in {'只要文字', '跳过'}:
        return 'ignore'
    if any(key in fragment for key in REDRAW_KEYS):
        return 'redraw'
    return None


def parse(response, ask):
    """Return {'word': bool|None, 'image_mode': str|None, 'ambiguous': [...]} for the asked items."""
    if not isinstance(response, str):
        raise ValueError('回答必须是文字')
    asked = [item for item in ITEMS if item in set(ask)]
    if not asked or set(ask) - set(ITEMS):
        raise ValueError('ask 只能包含 word、image')
    text = normalize(response)
    found = {item: set() for item in asked}

    def record(item, value):
        if item not in asked:
            raise ValueError(f'回答了未询问的项：{item}')
        found[item].add(value)

    def letter(item, value):
        table = WORD_LETTERS if item == 'word' else IMAGE_LETTERS
        found[item].add(table.get(value, 'invalid'))

    numbered = NUMBERED.findall(text)
    if numbered:
        for number, value in numbered:
            index = int(number) - 1
            if index >= len(asked):
                raise ValueError(f'回答了未询问的第 {number} 项')
            letter(asked[index], value)
        text = NUMBERED.sub(' ', text)
    elif len(asked) == 1 and LETTER_ONLY.match(text):
        letter(asked[0], LETTER_ONLY.match(text)[1])
        text = ''

    fragments = [part for part in SEPARATORS.split(text) if part]
    if len(asked) == 1 and fragments and not numbered:
        whole = ''.join(fragments) if len(fragments) > 1 else fragments[0]
        item = asked[0]
        if item == 'image':
            try:
                found['image'].add(reply_mode(response))
                fragments = []
            except ValueError:
                pass
        elif compact(text) in WORD_LABELS or whole in WORD_YES or whole in WORD_NO:
            found['word'].add(WORD_LABELS.get(compact(text), whole in WORD_YES))
            fragments = []
    for fragment in fragments:
        if fragment in GENERIC:
            if len(asked) == 1:
                if asked[0] == 'word':
                    found['word'].add(fragment in WORD_YES if fragment in WORD_YES | WORD_NO else 'invalid')
                else:
                    try:
                        found['image'].add(reply_mode(fragment))
                    except ValueError:
                        found['image'].add('invalid')
            continue  # Generic words cannot tell which of two questions they answer.
        word, image = word_value(fragment), image_value(fragment)
        if word is not None and image is not None and any(neg in fragment for neg in NEGATIONS):
            for item in asked:
                found[item].add('invalid')  # A negation spanning both choices is unclear.
            continue
        if word is not None:
            record('word', word)
        if image is not None:
            record('image', image)
    if 'image' in found and found['image'] == {'redraw', 'redraw:original'}:
        found['image'] = {'redraw:original'}  # e.g. "重绘，失败时保留原图"
    result = {'word': None, 'image_mode': None, 'image_fallback': None, 'ambiguous': []}
    for item in asked:
        values = found[item]
        if len(values) == 1 and 'invalid' not in values:
            value = values.pop()
            if item == 'word':
                result['word'] = value
            else:
                result['image_mode'] = 'redraw' if value.startswith('redraw') else value
                if result['image_mode'] == 'redraw':
                    result['image_fallback'] = 'original' if value == 'redraw:original' else 'placeholder'
        else:
            result['ambiguous'].append(item)
    return result


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('parse')
    p.add_argument('--ask', required=True, help='word, image or word,image: the items actually asked')
    p.add_argument('--response', required=True, help="The user's actual reply in the current chat")
    args = parser.parse_args()
    try:
        result = parse(args.response, [part.strip() for part in args.ask.split(',') if part.strip()])
    except ValueError as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(2 if result['ambiguous'] else 0)


if __name__ == '__main__':
    main()
