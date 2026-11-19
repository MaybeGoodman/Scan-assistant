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

ITEMS = ('word', 'image', 'generate')
SEPARATORS = re.compile(r'[，,、；;。！!？?\s~～…]+')
REPLY_SEPARATORS = re.compile(r'[，,、；;。！!？?\s.~～…]+')
NUMBERED = re.compile(r'([1-9])\s*[-.:：、．)）]?\s*([a-z])')
LETTER_ONLY = re.compile(r'^\s*([a-z])\s*$')
WORD_LETTERS = {'a': True, 'b': False}
# 'redraw:original' = redraw, and keep the original crop where a figure fails or is a photo.
IMAGE_LETTERS = {'a': 'redraw', 'b': 'ignore', 'c': 'preserve', 'd': 'redraw:original'}
WORD_KEYS = ('word', 'docx', '文档')
WORD_NO_OUTPUT = ('直接输出', '只要提取内容', '只输出内容', '不生成文档')
IMAGE_KEYS = ('图', '画', '绘', '插图')
# V1.0 (R08): the single post-extraction invitation to generate similar questions.
GENERATE_KEYS = ('同类题', '变式', '练习', '出题', '类似题', '举一反三', '相似题', '再出', '生成题')
GENERATE_LETTERS = {'a': True, 'b': False}
NEGATIONS = ('不要', '不用', '不需要', '无需', '不生成', '别', '不画', '不重绘', '忽略', '跳过', '不')
PRESERVE_KEYS = ('保留原图', '原图保留', '用原图', '原图即可', '保留图片原样')
NEGATED_PRESERVE = re.compile(r'(?:不要|不用|不需要|无需|别|不)\s*(?:保留原图|原图保留|用原图|保留图片原样|保留|用)?\s*原图')
REDRAW_KEYS = ('重绘', '重新绘制', '重画', '画出来', '画一下', '也要', '要图', '图也生成', '图片也处理', '绘制')
# Single-question image reply sets (previously duplicated in figure_workflow.py).
REPLY_YES = {'是', '可以', '需要', '继续', '要', '重绘', '重新绘制', '帮我画出来', '图片也处理', '图也生成',
             '好', '行', '对', '嗯', '没问题', '可', '画', '重画', '都要', '需要重绘', '要重绘', 'yes', 'y', 'ok', 'okay'}
REPLY_NO = {'否', '不需要', '不用', '跳过', '只要文字', '不要图片', '图片忽略',
            '不', '不要', '不行', '不是', '不画', '不重绘', '不用画', '不用重绘', '不需要重绘', '算了', '没必要', 'no', 'n'}
REPLY_PRESERVE = {'不用重绘，原图保留', '不重绘，保留原图', '保留原图', '原图保留', '用原图', '保留原图即可'}
REPLY_LEADING = '嗯哦噢喔那额呃'
REPLY_TRAILING = '的了吧啊呀哦呢嘛啦'
FILLER_WORDS = {'', '好', '嗯', '行', '对'}
GENERIC = {'是', '否', '好', '行', '对', '嗯', '可以', '可', '要', '不', '不要', '不行', '不是', '没问题', '需要',
           '不需要', '不用', '继续', '算了', '没必要', '好的', '是的', '可以的', '行的', '好吧', '嗯嗯', '都行',
           'ok', 'okay', 'yes', 'no', 'y', 'n'}
WORD_YES = {'是', '是的', '好', '好的', '可以', '可以的', '行', '对', '要', '需要', '需要的', '没问题', '嗯',
            'ok', 'okay', 'yes', 'y', '生成', '要的'}
WORD_NO = {'否', '不', '不要', '不用', '不需要', '不行', '不是', '算了', '没必要', 'no', 'n'}
# Option labels shown by multiple-choice tools.
WORD_LABELS = {'生成word(.docx)': True, '生成word': True, '直接输出提取内容': False}
IMAGE_LABELS = {'重新绘制插图': 'redraw', '重新绘制': 'redraw', '不要图片': 'ignore', '保留原图': 'preserve',
                '重新绘制插图(失败处留占位)': 'redraw',
                '重新绘制,失败或照片时保留原图': 'redraw:original',
                '重新绘制，失败或照片时保留原图': 'redraw:original',
                '重新绘制(失败或照片时保留原图)': 'redraw:original',
                '重新绘制插图(失败或照片时保留原图)': 'redraw:original'}


def normalize(text):
    return unicodedata.normalize('NFKC', text).strip().lower()


def compact(text):
    return re.sub(r'\s+', '', text)


def _reply_word(part):
    """Map one normalized reply fragment to an image mode, or None when unknown."""
    for candidate in (part, part.lower()):
        if candidate in REPLY_YES:
            return 'redraw'
        if candidate in REPLY_NO:
            return 'ignore'
        if candidate in REPLY_PRESERVE:
            return 'preserve'
    trimmed = part.lstrip(REPLY_LEADING).rstrip(REPLY_TRAILING) or part
    trimmed = trimmed.rstrip(REPLY_TRAILING) or trimmed
    if trimmed != part:
        return _reply_word(trimmed)
    return None


def reply_mode(response):
    """Parse a standalone reply to the image-handling confirmation question."""
    if response is None:
        return None
    response = response.strip()
    whole = REPLY_SEPARATORS.sub('，', response).strip('，')
    if whole in REPLY_PRESERVE:
        return 'preserve'
    fragments = [p for p in REPLY_SEPARATORS.split(response) if p]
    modes = {_reply_word(p) for p in fragments}
    # Filler-only fragments such as "嗯" or "好的" may accompany a clear answer.
    fillers = {_reply_word(p) for p in fragments
               if p.lstrip(REPLY_LEADING).rstrip(REPLY_TRAILING) in FILLER_WORDS}
    decisive = modes - ({'redraw'} if fillers == {'redraw'} and len(modes) > 1 else set())
    if not fragments or None in decisive or len(decisive) != 1:
        raise ValueError('Ambiguous redraw reply; clarify the active image question')
    return decisive.pop()


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
    if NEGATED_PRESERVE.search(fragment):
        return False
    return '原图' in fragment and ('失败' in fragment or '照片' in fragment)


def image_value(fragment):
    if compact(fragment) in IMAGE_LABELS:
        return IMAGE_LABELS[compact(fragment)]
    negated_preserve = bool(NEGATED_PRESERVE.search(fragment))
    if fallback_fragment(fragment) or (not negated_preserve
                                       and any(key in fragment for key in PRESERVE_KEYS)
                                       and any(key in fragment for key in REDRAW_KEYS)):
        return 'redraw:original'
    if negated_preserve:
        if any(key in fragment for key in REDRAW_KEYS):
            return 'redraw'
        return None  # Rejecting original-image preservation does not pick between redraw and ignore.
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


def generate_value(fragment):
    if any(key in fragment for key in GENERATE_KEYS):
        return False if any(neg in fragment for neg in NEGATIONS) else True
    if fragment in {'不生成', '只要原题', '只提取', '不用出题'}:
        return False
    return None


def _strip_filler(fragment):
    return fragment.lstrip(REPLY_LEADING).rstrip(REPLY_TRAILING)


_GEN_NO = re.compile(r'^(?:暂时?|先|目前|这次|今天)?(?:不要|不用|不需要|无需|不生成|算了|没必要|不|no|n)')


def _generate_single(fragments, whole):
    value = generate_value(whole)
    if value is not None:
        return value
    if whole in WORD_YES or whole in WORD_NO:
        return whole in WORD_YES
    # Evaluate fragment by fragment so "好的，不需要了" does not match leading "好".
    non_filler = [f for f in fragments if _strip_filler(f) not in FILLER_WORDS]
    target = non_filler or fragments
    is_no = lambda f: f in WORD_NO or _strip_filler(f) in WORD_NO or bool(_GEN_NO.match(f))
    has_no = any(is_no(f) for f in target)
    has_yes = any(f in WORD_YES or any(f.startswith(key) for key in ('要', '好', '可以', '行', '需要'))
                  for f in target if not is_no(f))
    if has_no and not has_yes:
        return False
    if has_yes and not has_no and not any(neg in whole for neg in NEGATIONS):
        return True
    return None


def parse(response, ask):
    """Return {'word', 'image_mode', 'image_fallback', 'generate', 'ambiguous'} for the asked items."""
    if not isinstance(response, str):
        raise ValueError('回答必须是文字')
    asked = [item for item in ITEMS if item in set(ask)]
    if not asked or set(ask) - set(ITEMS):
        raise ValueError('ask 只能包含 word、image、generate')
    text = normalize(response)
    found = {item: set() for item in asked}

    def record(item, value):
        if item not in asked:
            raise ValueError(f'回答了未询问的项：{item}')
        found[item].add(value)

    def letter(item, value):
        table = {'word': WORD_LETTERS, 'image': IMAGE_LETTERS, 'generate': GENERATE_LETTERS}[item]
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
            if compact(text) in IMAGE_LABELS:
                found['image'].add(IMAGE_LABELS[compact(text)])
                fragments = []
            elif not NEGATED_PRESERVE.search(text):
                try:
                    found['image'].add(reply_mode(response))
                    fragments = []
                except ValueError:
                    pass
        elif item == 'generate':
            value = _generate_single(fragments, whole)
            if value is not None:
                found['generate'].add(value)
                fragments = []
        elif compact(text) in WORD_LABELS or whole in WORD_YES or whole in WORD_NO:
            found['word'].add(WORD_LABELS.get(compact(text), whole in WORD_YES))
            fragments = []
    for fragment in fragments:
        if fragment in GENERIC:
            if len(asked) == 1:
                if asked[0] in {'word', 'generate'}:
                    found[asked[0]].add(fragment in WORD_YES if fragment in WORD_YES | WORD_NO else 'invalid')
                else:
                    try:
                        found['image'].add(reply_mode(fragment))
                    except ValueError:
                        found['image'].add('invalid')
            continue  # Generic words cannot tell which of two questions they answer.
        generate = generate_value(fragment) if 'generate' in asked else None
        if generate is not None:
            record('generate', generate)
            continue
        if asked == ['generate']:
            found['generate'].add('invalid')  # Unrecognised reply to the only question: ask again.
            continue
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
    if 'generate' in asked:
        result['generate'] = None  # Present only when asked, so 0.8.1 callers see the same keys.
    for item in asked:
        values = found[item]
        if len(values) == 1 and 'invalid' not in values:
            value = values.pop()
            if item == 'word':
                result['word'] = value
            elif item == 'generate':
                result['generate'] = value
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
    p.add_argument('--ask', required=True, help='word, image, generate or a comma list: the items actually asked')
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
