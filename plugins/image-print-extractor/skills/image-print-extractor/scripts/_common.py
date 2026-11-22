"""Shared internal helpers for Scan-assistant scripts (file I/O, hashing, path safety, constants)."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

RUN_ID = re.compile(r'[A-Za-z0-9_-]{1,32}')
OUTPUT_MODES = ('original', 'student')
CHEMISTRY_FORMATS = ('native', 'source')
PASTE_TARGETS = ('axmath', 'markdown')
BLANK_LATEX = ('underline', 'escaped')
# Labels that usually introduce answer/analysis material. Requires either brackets around the
# keyword, a colon after the keyword, or "故选" followed by an option/colon, so ordinary stems
# like "答题时..." or "解答下列各题" do not false-positive while "【答案】B" is caught everywhere.
ANSWER_LABEL = re.compile(
    r'^\s*(?:[【\[（(]\s*(?:参考答案|答案|解析|解答|详解|点拨|评分|答)\s*[】\]）)]\s*[:：]?'
    r'|(?:参考答案|答案|解析|解答|详解|点拨|评分|答)\s*[:：]'
    r'|故选(?:\s*[A-H（(]|[:：]))'
)


def sha256(path):
    """Streaming SHA-256 hex digest (1 MiB chunks) to avoid loading large files into memory."""
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_new(path, value):
    """Create a new UTF-8 JSON file exclusively; fails if the file already exists."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def replace_atomic(path, value):
    """Atomically replace a JSON state file via a unique temporary file in the same directory."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    temporary = Path(tmp_name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def local_path(base, relative, *, error_message='Path must be relative and inside the base directory'):
    """Resolve a relative path and ensure it cannot escape ``base``."""
    if not isinstance(relative, (str, Path)) or not str(relative):
        raise ValueError(error_message)
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError(error_message)
    base_resolved = Path(base).resolve()
    resolved = (base_resolved / path).resolve()
    if not resolved.is_relative_to(base_resolved):
        raise ValueError(error_message)
    return resolved


def iter_texts(item):
    """Yield (path, string) for every transcribed string inside a block, run or table cell."""
    if 'text' in item and isinstance(item['text'], str):
        yield 'text', item['text']
    if 'latex' in item and isinstance(item['latex'], str):
        yield 'latex', item['latex']
    for key in ('runs', 'cells'):
        for index, child in enumerate(item.get(key, []) or []):
            if isinstance(child, dict):
                for path, text in iter_texts(child):
                    yield f'{key}[{index}].{path}', text
