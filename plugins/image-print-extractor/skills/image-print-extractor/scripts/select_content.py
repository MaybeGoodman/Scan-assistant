"""Apply host-reviewed semantic selection; never classify text or modify pixels."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

CATEGORIES = frozenset({
    'MAIN_CONTENT', 'SUPPORTING_CONTENT', 'ADVERTISEMENT', 'WATERMARK',
    'BRANDING', 'CONTACT', 'QR_PROMOTION', 'DECORATION', 'HEADER_FOOTER',
    'PAGE_NUMBER', 'HANDWRITING', 'UNKNOWN',
})
NOISE = CATEGORIES - {'MAIN_CONTENT', 'SUPPORTING_CONTENT', 'HANDWRITING', 'UNKNOWN'}
SCOPES = frozenset({'main', 'body', 'all-printed', 'all-text'})


def decision(item, *, scope='main', preserve=(), include_handwriting=False):
    """Return keep/reason/review using semantic evidence supplied by the host."""
    if scope not in SCOPES or not set(preserve) <= CATEGORIES:
        raise ValueError('Invalid extraction scope or preserved category')
    annotation = item.get('selection', {})
    if not isinstance(annotation, dict):
        raise ValueError('selection must be an object')
    category = annotation.get('category', 'UNKNOWN')
    relation = annotation.get('relation', 'unknown')
    certainty = annotation.get('certainty', 'uncertain')
    reason = annotation.get('reason', '')
    if (category not in CATEGORIES or relation not in {'main', 'supporting', 'unrelated', 'unknown'}
            or certainty not in {'high', 'uncertain'} or not isinstance(reason, str)):
        raise ValueError('Invalid semantic selection metadata')
    if category == 'HANDWRITING':
        keep = scope == 'all-text' or include_handwriting or category in preserve
        if not keep and certainty != 'high':
            return True, 'uncertain handwriting classification', True
        return keep, 'handwriting included' if keep else 'default handwriting exclusion', False
    if category in preserve:
        return True, 'explicit user preservation', False
    if scope in {'all-printed', 'all-text'} and item.get('type') != 'image':
        return True, 'explicit all-textual-content scope', False
    if relation in {'main', 'supporting'}:
        return True, 'protect related content', category in NOISE
    if category in {'MAIN_CONTENT', 'SUPPORTING_CONTENT', 'UNKNOWN'}:
        return True, 'protect main or uncertain content', relation == 'unrelated'
    if certainty == 'high' and relation == 'unrelated' and reason.strip():
        return False, reason, False
    return True, 'insufficient evidence for removal', True


def select_document(document, *, scope='main', preserve=(), include_handwriting=False):
    if not isinstance(document, dict) or not isinstance(document.get('blocks'), list):
        raise ValueError('Document must contain a blocks list')
    if scope not in SCOPES or not set(preserve) <= CATEGORIES:
        raise ValueError('Invalid extraction scope or preserved category')
    records = []

    def visit(item, location, *, cell=False):
        if not isinstance(item, dict):
            raise ValueError('Content elements must be objects')
        keep, reason, review = decision(item, scope=scope, preserve=preserve,
                                        include_handwriting=include_handwriting)
        # Do not let a noise-labelled container swallow protected descendants.
        if not keep and item.get('selection', {}).get('category') != 'HANDWRITING':
            children = item.get('runs', []) + item.get('cells', [])
            if any(decision(child, scope=scope, preserve=preserve,
                            include_handwriting=include_handwriting)[0] for child in children):
                keep, reason, review = True, 'protect retained descendants', True
        records.append({'location': location, 'source': item.get('source'),
                        'selection': deepcopy(item.get('selection', {})),
                        'action': 'keep' if keep else 'clear-cell' if cell else 'remove',
                        'reason': reason, 'needs_review': review})
        if not keep:
            if not cell:
                return None
            result = {k: deepcopy(v) for k, v in item.items()
                      if k not in {'selection', 'text', 'runs'}}
            result['text'] = ''
            return result
        result = deepcopy(item)
        result.pop('selection', None)
        if 'runs' in result:
            if not isinstance(result['runs'], list):
                raise ValueError('runs must be a list')
            result['runs'] = [filtered for i, run in enumerate(result['runs'])
                              if (filtered := visit(run, f'{location}.runs[{i}]')) is not None]
        if result.get('type') == 'table':
            if not isinstance(result.get('cells'), list):
                raise ValueError('Table must contain cells')
            result['cells'] = [visit(value, f'{location}.cells[{i}]', cell=True)
                               for i, value in enumerate(result['cells'])]
        return result

    result = deepcopy(document)
    result['blocks'] = [filtered for i, block in enumerate(document['blocks'])
                        if (filtered := visit(block, f'blocks[{i}]')) is not None]
    report = {'scope': scope, 'preserve': sorted(set(preserve)),
              'include_handwriting': include_handwriting, 'records': records,
              'needs_review': sum(record['needs_review'] for record in records)}
    return result, report


def select_file(source, output, report_path, **options):
    source, output, report_path = (Path(p).resolve() for p in (source, output, report_path))
    if len({source, output, report_path}) != 3:
        raise ValueError('Input, output and report must be separate files')
    if output.parent != source.parent:
        raise ValueError('Keep output JSON beside input to preserve relative PNG paths')
    if output.suffix.lower() != '.json' or report_path.suffix.lower() != '.json':
        raise ValueError('Output and report must be JSON files')
    if output.exists() or report_path.exists():
        raise FileExistsError('Selection output or report already exists')
    result, report = select_document(json.loads(source.read_text(encoding='utf-8')), **options)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also protects against a concurrent writer.
    with report_path.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    with output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('--output', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--scope', choices=sorted(SCOPES), default='main')
    parser.add_argument('--preserve', action='append', choices=sorted(CATEGORIES), default=[])
    parser.add_argument('--include-handwriting', action='store_true')
    args = parser.parse_args()
    select_file(args.source, args.output, args.report, scope=args.scope,
                preserve=args.preserve, include_handwriting=args.include_handwriting)


if __name__ == '__main__':
    main()
