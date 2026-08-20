from __future__ import annotations

import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "campaigns.db"

EXPECTED = [
    "BES Teminatlı Finansman",
    "Eğitim Finansmanı",
    "Hac ve Umre Finansmanı",
    "Jet Finansman",
    "Motosiklet, ATV , Bisiklet",
    "Pratik Finansman Kart",
    "SMS’ li Finansman",
    "İhtiyaç Finansmanı",
    "Şubesiz Umre Finansmanı",
]


def get_product(con, name):
    return con.execute(
        """
        SELECT d.product_id,d.product_name,d.minimum_financing_amount,
               d.maximum_financing_amount,d.maximum_maturity_months,d.interest_free
        FROM live_standard_product_details d
        JOIN live_campaigns c ON c.id=d.product_id
        WHERE c.is_current=1 AND c.record_kind='standard_product'
          AND d.bank_name='Albaraka Türk' AND d.product_family='İhtiyaç Finansmanı'
          AND d.product_name=?
        """,
        (name,),
    ).fetchone()


def feature(con, pid, key):
    row = con.execute(
        "SELECT feature_value FROM live_product_features WHERE product_id=? AND feature_key=?",
        (pid, key),
    ).fetchone()
    return str(row[0] or "") if row else ""


def bands(con, pid):
    return {
        (r[0], r[1], r[2])
        for r in con.execute(
            "SELECT min_amount,max_amount,max_maturity_months FROM live_product_amount_maturity_rules WHERE product_id=?",
            (pid,),
        ).fetchall()
    }


def main() -> int:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    warnings = []
    print("=" * 96)
    print("ALBARAKA TÜRK — İHTİYAÇ FİNANSMANI FINAL AUDIT V9")
    print("=" * 96)

    current = con.execute(
        """
        SELECT d.product_name FROM live_standard_product_details d
        JOIN live_campaigns c ON c.id=d.product_id
        WHERE c.is_current=1 AND c.record_kind='standard_product'
          AND d.bank_name='Albaraka Türk' AND d.product_family='İhtiyaç Finansmanı'
        ORDER BY d.product_name
        """
    ).fetchall()
    names = [r[0] for r in current]
    print("Güncel İhtiyaç ürünü:", len(names))
    print("Ürünler:", " | ".join(names))
    for name in EXPECTED:
        if name not in names:
            warnings.append(f"Eksik ürün: {name}")

    # BES
    p = get_product(con, "BES Teminatlı Finansman")
    if p:
        if feature(con,p['product_id'],'application_channel') != 'Şube':
            warnings.append('BES kanal Şube değil')
        if 'BES birikimi' not in feature(con,p['product_id'],'security_type'):
            warnings.append('BES teminat metriği eksik')
        if '20 puan' not in feature(con,p['product_id'],'cost_advantage'):
            warnings.append('BES 20 puan indirim metriği eksik')
        if 'Nakit kullandırım yok' not in feature(con,p['product_id'],'transaction_structure'):
            warnings.append('BES nakit kullandırım yok / işlem yapısı eksik')

    # Eğitim
    p = get_product(con, "Eğitim Finansmanı")
    if p:
        if p['maximum_maturity_months'] != 12:
            warnings.append('Eğitim 12 ay azami vade eksik')
        if feature(con,p['product_id'],'digital_process') != 'Evet':
            warnings.append('Eğitim dijital süreç (Jet üzerinden) eksik')
        target = feature(con,p['product_id'],'target_segment')
        for token in ('Bireysel','Serbest Meslek','Tüzel Kişi'):
            if token not in target:
                warnings.append(f'Eğitim hedef kitle eksik: {token}')
        rep = feature(con,p['product_id'],'repayment_structure')
        if '12 aya kadar' not in rep or 'eşit veya değişken' not in rep:
            warnings.append('Eğitim ödeme yapısı eksik')

    # Hac ve Umre
    p = get_product(con, "Hac ve Umre Finansmanı")
    if p:
        expected={(None,125000.0,36),(125000.0,250000.0,24),(250000.0,None,12)}
        if not expected.issubset(bands(con,p['product_id'])):
            warnings.append('Hac ve Umre 36/24/12 vade bantları eksik')
        target = feature(con,p['product_id'],'target_segment')
        for token in ('Bireysel','Serbest Meslek','Tüzel Kişi'):
            if token not in target:
                warnings.append(f'Hac/Umre hedef kitle eksik: {token}')
        if feature(con,p['product_id'],'digital_process') != 'Evet':
            warnings.append('Hac/Umre Jet üzerinden dijital süreç eksik')

    # Jet
    p = get_product(con, "Jet Finansman")
    if p:
        if p['minimum_financing_amount'] != 1000.0 or p['maximum_financing_amount'] != 60000.0:
            warnings.append('Jet ürün limiti 1.000-60.000 TL değil')
        expected={(None,50000.0,36),(50000.0,100000.0,24),(100000.0,None,12)}
        if not expected.issubset(bands(con,p['product_id'])):
            warnings.append('Jet yayımlanan 36/24/12 vade bantları eksik')
        if '45 gün' not in feature(con,p['product_id'],'repayment_structure'):
            warnings.append('Jet ilk taksit 45 gün bilgisi eksik')

    # Motosiklet
    p = get_product(con, "Motosiklet, ATV , Bisiklet")
    if p:
        expected={(None,125000.0,36),(125000.0,250000.0,24),(250000.0,None,12)}
        if not expected.issubset(bands(con,p['product_id'])):
            warnings.append('Motosiklet 36/24/12 vade bantları eksik')
        if 'Aylık eşit taksit' not in feature(con,p['product_id'],'repayment_structure'):
            warnings.append('Motosiklet aylık eşit taksit bilgisi eksik')

    # Pratik
    p = get_product(con, "Pratik Finansman Kart")
    if p:
        if p['minimum_financing_amount'] != 250.0 or p['maximum_financing_amount'] != 150000.0:
            warnings.append('Pratik limit 250-150.000 TL değil')
        expected={(None,125000.0,36),(125000.0,150000.0,24)}
        if not expected.issubset(bands(con,p['product_id'])):
            warnings.append('Pratik 36/24 ay vade bantları eksik')
        rep=feature(con,p['product_id'],'repayment_structure')
        if '2 ay sonraya otomatik atanır' not in rep or '3 aya kadar ötelenebilir' not in rep:
            warnings.append('Pratik ilk taksit/öteleme yapısı eksik')

    # SMS
    p = get_product(con, "SMS’ li Finansman")
    if p:
        if 'SMS 4462' not in feature(con,p['product_id'],'application_channel'):
            warnings.append('SMS 4462 kanal bilgisi eksik')
        tx=feature(con,p['product_id'],'transaction_structure')
        if 'SMS ile ön onay' not in tx or 'şubede' not in tx:
            warnings.append('SMS ön onay / şubede kullanım yapısı eksik')

    # Genel ihtiyaç
    p = get_product(con, "İhtiyaç Finansmanı")
    if p:
        if p['maximum_financing_amount'] is not None:
            warnings.append('Genel İhtiyaç için kaynakta olmayan sahte maksimum tutar var')
        expected={(None,125000.0,36),(125000.0,250000.0,24),(250000.0,None,12)}
        if not expected.issubset(bands(con,p['product_id'])):
            warnings.append('Genel İhtiyaç 36/24/12 vade bantları eksik')
        if 'Esnek ödeme' not in feature(con,p['product_id'],'repayment_structure'):
            warnings.append('Genel İhtiyaç esnek ödeme bilgisi eksik')

    # Şubesiz Umre
    p = get_product(con, "Şubesiz Umre Finansmanı")
    if p:
        if p['maximum_financing_amount'] != 50000.0:
            warnings.append('Şubesiz Umre maksimum 50.000 TL eksik')
        if int(p['interest_free'] or 0) != 1:
            warnings.append('Şubesiz Umre vade/kâr paysız işareti eksik')
        rep=feature(con,p['product_id'],'repayment_structure')
        if '4 eşit taksit' not in rep or 'Vade farksız' not in rep:
            warnings.append('Şubesiz Umre 4 eşit taksit / vade farksız bilgisi eksik')
        if feature(con,p['product_id'],'digital_process') != 'Evet':
            warnings.append('Şubesiz Umre tamamen dijital süreç eksik')

    print("Uyarı:", len(warnings))
    for w in warnings:
        print(" -", w)
    print("SONUÇ:", "OK" if not warnings else "KONTROL GEREKİYOR")
    con.close()
    return 0 if not warnings else 1


if __name__ == '__main__':
    raise SystemExit(main())
