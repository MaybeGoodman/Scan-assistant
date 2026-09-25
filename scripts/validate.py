"""Offline package checks; does not claim complete remote schema validation."""
import json
from pathlib import Path
import yaml

root = Path(__file__).resolve().parents[1]
catalog = json.loads((root / '.agents/plugins/marketplace.json').read_text(encoding='utf-8'))
for entry in catalog['plugins']:
    path = entry['source']['path']
    assert path.startswith('./') and '..' not in Path(path).parts
    plugin = root / path
    portable = json.loads((plugin / 'plugin.json').read_text(encoding='utf-8'))
    legacy = json.loads((plugin / '.codex-plugin/plugin.json').read_text(encoding='utf-8'))
    assert portable['$schema'] == 'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json'
    for key in ('name', 'version', 'description', 'author', 'repository'):
        assert portable[key] == legacy[key], key
    assert portable['name'] == entry['name'] == plugin.name
    ui = portable['extensions']['com.openai']['interface']
    assert ui == legacy['interface']
    for key in ('composerIcon', 'logo'):
        assert (plugin / ui[key]).is_file()
    assert entry['policy']['installation'] == 'AVAILABLE'
    assert entry['policy']['authentication'] == 'ON_INSTALL'
    assert entry['category'] == 'Productivity'
    for skill in (plugin / 'skills').iterdir():
        text = (skill / 'SKILL.md').read_text(encoding='utf-8')
        metadata = yaml.safe_load(text.split('---', 2)[1])
        assert metadata['name'] == skill.name and metadata['description']
        ui = yaml.safe_load((skill / 'agents/openai.yaml').read_text(encoding='utf-8'))['interface']
        for key in ('icon_small', 'icon_large'):
            assert (skill / ui[key]).is_file()
        assert '$' + skill.name in ui['default_prompt']
print('Package checks passed')
