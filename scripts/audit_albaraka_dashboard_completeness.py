from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path('data/campaigns.db')

EXPECTED_FAMILIES = {
    'Alışveriş Finansmanı': 1,
    'Araç Finansmanı': 5,
    'Arsa Finansmanı': 2,
    'Gayri Nakdi Finansman': 5,
    'Konut Finansmanı': 1,
    'Leasing': 1,
    'Tarım Finansmanı': 6,
    'Ticari Finansman': 10,
    'İhtiyaç Finansmanı': 8,
    'İş Yeri Finansmanı': 1,
}

EXPECTED_METRICS = {
    ('Deniz Taşıtları Finansmanı','bireysel'): {'maximum_maturity_months': 36},
    ('Togg Finansmanı','bireysel'): {'maximum_maturity_months': 48, 'maximum_financing_ratio': 70.0},
    ('2B Arazi Finansmanı','bireysel'): {'maximum_maturity_months': 60},
    ('Arsa Finansmanı','bireysel'): {'maximum_maturity_months': 60, 'maximum_financing_ratio': 100.0},
    ('Konut Finansmanı','bireysel'): {'maximum_maturity_months': 120},
    ('Leasing - Finansal Kiralama','ticari'): {'maximum_financing_ratio': 100.0},
    ('Bitkisel Üretim Finansmanı','ticari'): {'maximum_maturity_months': 24},
    ('Biçerdöver Finansmanı','ticari'): {'maximum_maturity_months': 48},
    ('Makine Ekipman Finansmanı','ticari'): {'maximum_maturity_months': 48},
    ('Seracılık Finansmanı','ticari'): {'maximum_maturity_months': 48},
    ('Tarla Alım Finansmanı','ticari'): {'maximum_maturity_months': 48},
    ('Traktör Finansmanı','ticari'): {'maximum_maturity_months': 48},
    ('Jet Ticari Finansman','ticari'): {'maximum_financing_amount': 2_000_000.0},
    ('Eğitim Finansmanı','bireysel'): {'maximum_maturity_months': 12},
    ('Jet Finansman','bireysel'): {'minimum_financing_amount': 1_000.0, 'maximum_financing_amount': 60_000.0, 'maximum_maturity_months': 36},
    ('Motosiklet, ATV , Bisiklet','bireysel'): {'maximum_maturity_months': 36},
    ('Pratik Finansman Kart','bireysel'): {'minimum_financing_amount': 250.0, 'maximum_financing_amount': 150_000.0, 'maximum_maturity_months': 36},
    ('İhtiyaç Finansmanı','bireysel'): {'maximum_financing_amount': None, 'maximum_maturity_months': 36},
    ('Şubesiz Umre Finansmanı','bireysel'): {'maximum_financing_amount': 50_000.0, 'interest_free': 1},
    ('İş Yeri Finansmanı','bireysel'): {'maximum_maturity_months': 60, 'maximum_financing_ratio': 100.0},
}


def main() -> int:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    errors: list[str] = []

    total = con.execute("""
        SELECT COUNT(*) FROM live_campaigns
        WHERE bank_name='Albaraka Türk'
          AND record_kind='standard_product'
          AND is_current=1
    """).fetchone()[0]
    if total != 40:
        errors.append(f'Güncel ürün 40 olmalı, bulunan={total}')

    families = dict(con.execute("""
        SELECT d.product_family, COUNT(*)
        FROM live_campaigns c
        JOIN live_standard_product_details d ON d.product_id=c.id
        WHERE c.bank_name='Albaraka Türk'
          AND c.record_kind='standard_product'
          AND c.is_current=1
        GROUP BY d.product_family
    """).fetchall())
    if families != EXPECTED_FAMILIES:
        errors.append(f'Aile dağılımı farklı: {families}')

    for (name, scope), expected in EXPECTED_METRICS.items():
        row = con.execute("""
            SELECT d.*
            FROM live_campaigns c
            JOIN live_standard_product_details d ON d.product_id=c.id
            WHERE c.bank_name='Albaraka Türk'
              AND c.is_current=1
              AND d.product_name=?
              AND d.scope=?
        """, (name, scope)).fetchone()
        if row is None:
            errors.append(f'Ürün bulunamadı: {name} [{scope}]')
            continue
        for key, value in expected.items():
            actual = row[key]
            if actual != value:
                errors.append(f'{name} {key}: beklenen={value!r}, bulunan={actual!r}')

    # 40/40 ürünün kaynak dayanaklı amacı olmalı.
    purpose_count = con.execute("""
        SELECT COUNT(DISTINCT c.id)
        FROM live_campaigns c
        JOIN live_product_features f ON f.product_id=c.id
        WHERE c.bank_name='Albaraka Türk'
          AND c.record_kind='standard_product'
          AND c.is_current=1
          AND f.feature_key='usage_purpose'
          AND TRIM(f.feature_value)<>''
          AND TRIM(COALESCE(f.source_text,''))<>''
    """).fetchone()[0]
    if purpose_count != 40:
        errors.append(f'Kaynak dayanaklı amaç kapsamı 40/40 değil: {purpose_count}/40')

    # ELÜS bilgisi kardeş ürünlere sızmamalı.
    contamination = con.execute("""
        SELECT c.title, f.feature_key, f.feature_value
        FROM live_campaigns c
        JOIN live_product_features f ON f.product_id=c.id
        WHERE c.bank_name='Albaraka Türk'
          AND c.title <> 'Elüs Teminatlı Kredi'
          AND (
              f.feature_value LIKE '%ELÜS%'
              OR f.feature_value LIKE '%Tarımsal ürün karşılığı%'
          )
    """).fetchall()
    if contamination:
        errors.append(f'Cross-product contamination: {[tuple(x) for x in contamination]}')

    counts = {
        'amount_maturity': con.execute("""SELECT COUNT(*) FROM live_product_amount_maturity_rules r JOIN live_campaigns c ON c.id=r.product_id WHERE c.bank_name='Albaraka Türk'""").fetchone()[0],
        'pricing': con.execute("""SELECT COUNT(*) FROM live_product_pricing_tiers r JOIN live_campaigns c ON c.id=r.product_id WHERE c.bank_name='Albaraka Türk'""").fetchone()[0],
        'fee': con.execute("""SELECT COUNT(*) FROM live_product_fee_rules r JOIN live_campaigns c ON c.id=r.product_id WHERE c.bank_name='Albaraka Türk'""").fetchone()[0],
        'offer': con.execute("""SELECT COUNT(*) FROM live_product_offer_rules r JOIN live_campaigns c ON c.id=r.product_id WHERE c.bank_name='Albaraka Türk'""").fetchone()[0],
        'features': con.execute("""SELECT COUNT(*) FROM live_product_features r JOIN live_campaigns c ON c.id=r.product_id WHERE c.bank_name='Albaraka Türk'""").fetchone()[0],
    }

    togg = con.execute("""
        SELECT pricing_variant, financing_amount, maturity_months, profit_share_rate
        FROM live_product_pricing_tiers r
        JOIN live_campaigns c ON c.id=r.product_id
        WHERE c.bank_name='Albaraka Türk'
          AND c.title='Togg Finansmanı'
        ORDER BY pricing_variant, maturity_months
    """).fetchall()
    if len(togg) != 6 or any(row['financing_amount'] is None for row in togg):
        errors.append('Togg fiyatlama matrisi 6 tam satır değil.')

    umre = con.execute("""
        SELECT max_amount, max_installments, interest_free
        FROM live_product_offer_rules r
        JOIN live_campaigns c ON c.id=r.product_id
        WHERE c.bank_name='Albaraka Türk'
          AND c.title='Şubesiz Umre Finansmanı'
    """).fetchall()
    if not any(r['max_amount']==50000.0 and r['max_installments']==4 and r['interest_free']==1 for r in umre):
        errors.append('Şubesiz Umre 50.000 TL / 4 taksit / vade farksız kuralı eksik.')

    con.close()

    print('=' * 80)
    print('ALBARAKA — DASHBOARD EKSİKSİZLİK AUDIT')
    print('=' * 80)
    print('Güncel ürün:', total)
    print('Aile:', len(families))
    print('Kaynak dayanaklı amaç:', f'{purpose_count}/40')
    print('Tutar-vade kuralı:', counts['amount_maturity'])
    print('Fiyatlama satırı:', counts['pricing'])
    print('Masraf kuralı:', counts['fee'])
    print('Özel koşul:', counts['offer'])
    print('Nitel özellik:', counts['features'])
    print('Cross-product contamination:', len(contamination))
    print('Uyarı:', len(errors))
    if errors:
        for e in errors:
            print(' -', e)
        return 1
    print('SONUÇ: OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
