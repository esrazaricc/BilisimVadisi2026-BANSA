import json
from pathlib import Path


def _ziraat_cfg():
    data = json.loads(Path('config/standard_product_sources.json').read_text(encoding='utf-8'))
    for bank in data['banks']:
        if bank.get('name') == 'Ziraat Katılım':
            return bank
    raise AssertionError('Ziraat Katılım config bulunamadı')


def test_ziraat_finansman_is_birlikleri_current_path_is_used_everywhere():
    bank = _ziraat_cfg()
    current = '/ticari/finansman-urunleri/finansman_is_birlikleri'
    stale = '/ticari/finansman-urunleri/finansman-is-birlikleri'

    serialized = json.dumps(bank, ensure_ascii=False)
    assert stale not in serialized

    listing = next(
        page for page in bank['listing_pages']
        if current in page['url']
    )
    assert listing['url'] == f"https://www.ziraatkatilim.com.tr{current}"
    assert listing['allowed_prefix'] == current + '/'

    ticari = next(rule for rule in bank['family_rules'] if rule['family_key'] == 'ticari_finansman')
    assert current + '/' in ticari['path_contains']
    assert current in bank['exclude_exact_paths']
