from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "campaigns.db"


def _one(con, sql, params=()):
    return con.execute(sql, params).fetchone()


def sqlite_audit(db: Path) -> tuple[int, int]:
    con = sqlite3.connect(db); con.row_factory=sqlite3.Row
    passed=failed=0
    def check(label, ok, detail=""):
        nonlocal passed,failed
        if ok:
            passed+=1; print(f"PASS | {label}")
        else:
            failed+=1; print(f"FAIL | {label} | {detail}")

    # Metadata completeness
    bad=_one(con,"select count(*) n from live_product_pricing_tiers where value_type is null or trim(value_type)='' or source_type is null or trim(source_type)='' ")["n"]
    check("Tüm pricing tier satırlarında value_type/source_type var", bad==0, f"bad={bad}")
    bad=_one(con,"select count(*) n from live_finance_fact_evidence where value_type is null or source_type is null")["n"]
    check("Finansal evidence kayıtlarında zorunlu metadata var", bad==0, f"bad={bad}")

    # Kuveyt examples
    rows=con.execute("""select d.product_name,p.value_type from live_product_pricing_tiers p join live_standard_product_details d on d.product_id=p.product_id join live_campaigns c on c.id=p.product_id where c.bank_name='Kuveyt Türk' and p.profit_share_rate in (4.82,4.52) and d.product_name in ('Eğitim Finansmanı','Hac-Umre Finansmanı','Seyahat Finansmanı','Tekne Tüketici Finansmanı','Alışveriş Finansmanı')""").fetchall()
    check("Kuveyt 4,82/4,52 örnek oranları example olarak etiketli", len(rows)>=5 and all(r['value_type']=='example' for r in rows), str([dict(r) for r in rows]))

    # Türkiye Finans koşullu/örnek bağlamı çıplak güncel oran gibi saklanmaz.
    tf_bad=_one(con,"""select count(*) n from live_product_pricing_tiers p join live_standard_product_details d on d.product_id=p.product_id join live_campaigns c on c.id=p.product_id where c.bank_name='Türkiye Finans' and (d.product_name like 'Arsa Finansmanı%' or d.product_name like 'İş yeri Finansmanı%' or d.product_name like 'İş Yeri Finansmanı%' or d.product_name like 'Taksitli Ticari Taşıt%' or d.product_name like 'Ticari Hat / Ticari Plaka%' or d.product_name like 'Konut Finansmanı%' or d.product_name like 'Dijital İhtiyaç Finansmanı%' or d.product_name like 'Trendyol Alışveriş Finansmanı%') and (p.value_type!='conditional_pricing' or p.conditions is null or trim(p.conditions)='')""")["n"]
    check("Türkiye Finans koşullu fiyatlamaları conditional_pricing + koşul metadata'sıyla tutuluyor",tf_bad==0,f"bad={tf_bad}")

    # TF digital need
    pid=_one(con,"""select c.id from live_campaigns c join live_standard_product_details d on d.product_id=c.id where c.bank_name='Türkiye Finans' and d.product_name like 'Dijital İhtiyaç Finansmanı%' and c.is_current=1 limit 1""")
    if pid:
        rr=con.execute("select min_amount,max_amount,max_maturity_months from live_product_amount_maturity_rules where product_id=? order by coalesce(min_amount,-1)",(pid['id'],)).fetchall()
        sig=[(r['min_amount'],r['max_amount'],r['max_maturity_months']) for r in rr]
        check("Türkiye Finans Dijital İhtiyaç 3 doğru vade bandı", sig==[(None,125000.0,36),(125000.0,250000.0,24),(250000.0,None,12)], str(sig))
    else: check("Türkiye Finans Dijital İhtiyaç bulundu",False)

    # Hayat
    r=_one(con,"""select c.id,d.minimum_financing_amount,d.maximum_financing_amount,d.maximum_maturity_months from live_campaigns c join live_standard_product_details d on d.product_id=c.id where c.bank_name='Hayat Finans' and d.product_name='Bana Bunu Al' and c.is_current=1""")
    check("Hayat Bana Bunu Al 500-50.000 TL / 18 ay", bool(r) and r['minimum_financing_amount']==500 and r['maximum_financing_amount']==50000 and r['maximum_maturity_months']==18, str(dict(r) if r else None))
    if r:
        n=_one(con,"select count(*) n from live_product_amount_maturity_rules where product_id=?",(r['id'],))['n']
        check("Bana Bunu Al genel 125/250 bin TL vade bantlarını ana ürün kuralı olarak taşımıyor",n==0,f"rows={n}")

    # Dunya
    r=_one(con,"""select c.id,d.vehicle_age_rules_text from live_campaigns c join live_standard_product_details d on d.product_id=c.id where c.bank_name='Dünya Katılım' and d.product_name='Araç Finansmanı' and c.is_current=1""")
    if r:
        rr=con.execute("select max_maturity_months from live_product_amount_maturity_rules where product_id=? order by coalesce(min_amount,-1)",(r['id'],)).fetchall()
        check("Dünya Araç 4 değer/vade bandı",[x['max_maturity_months'] for x in rr]==[48,36,24,12],str([dict(x) for x in rr]))
        check("Dünya Araç ikinci el azami yaş bilgisi",'12 yaşa kadar' in str(r['vehicle_age_rules_text'] or ''),str(r['vehicle_age_rules_text']))

    # Togg
    r=_one(con,"""select c.id from live_campaigns c join live_standard_product_details d on d.product_id=c.id where c.bank_name='Albaraka Türk' and d.product_name='Togg Finansmanı' and c.is_current=1""")
    if r:
        rr=con.execute("select financing_amount,maturity_months,value_type,conditions from live_product_pricing_tiers where product_id=?",(r['id'],)).fetchall()
        check("Albaraka TOGG 6 model/tutar/vade fiyatlama satırını koruyor",len(rr)==6 and all(x['financing_amount'] is not None and x['value_type']=='conditional_pricing' and x['conditions'] for x in rr),f"rows={len(rr)}")

    # 2B
    r=_one(con,"""select c.id,d.maximum_maturity_months,d.profit_share_rate,d.profit_share_rate_text from live_campaigns c join live_standard_product_details d on d.product_id=c.id where c.bank_name='Albaraka Türk' and d.product_name='2B Arazi Finansmanı' and c.is_current=1""")
    if r:
        fees=con.execute("select fee_type,waived from live_product_fee_rules where product_id=?",(r['id'],)).fetchall()
        waived={x['fee_type']:x['waived'] for x in fees}
        check("Albaraka 2B 60 ay ve sayısal olmayan güncel fiyatlama metni",r['maximum_maturity_months']==60 and r['profit_share_rate'] is None and 'Resmî fiyatlama' in str(r['profit_share_rate_text']),str(dict(r)))
        check("Albaraka 2B ekspertiz/ipotek ücretleri alınmıyor",waived.get('appraisal')==1 and waived.get('mortgage_establishment')==1,str(waived))

    # GES subtype
    r=_one(con,"""select c.id from live_campaigns c join live_standard_product_details d on d.product_id=c.id where c.bank_name='Kuveyt Türk' and d.product_name='Çatı GES Finansmanı' and d.scope='bireysel' and c.is_current=1""")
    if r:
        f=_one(con,"select feature_value from live_product_features where product_id=? and feature_key='comparison_subtype'",(r['id'],))
        check("Çatı GES alt türü Sürdürülebilir / Enerji",bool(f) and f['feature_value']=='Sürdürülebilir / Enerji',str(dict(f) if f else None))

    # Alışveriş ürünleri: ürün özel koşullar karşılaştırma verisinde korunuyor.
    r=_one(con,"""select c.id from live_campaigns c join live_standard_product_details d on d.product_id=c.id where c.bank_name='Kuveyt Türk' and d.product_name='LC Waikiki Alışveriş Finansmanı' and c.is_current=1""")
    if r:
        offer=_one(con,"select max_amount,max_maturity_months,max_installments,interest_free from live_product_offer_rules where product_id=?",(r['id'],))
        check("LC Waikiki 5.000 TL / 3 ay / vade farksız ürün koşulu korunuyor",bool(offer) and offer['max_amount']==5000 and offer['max_maturity_months']==3 and offer['max_installments']==3 and offer['interest_free']==1,str(dict(offer) if offer else None))
    else:
        check("LC Waikiki Alışveriş Finansmanı bulundu",False)

    r=_one(con,"""select d.shopping_general_limit_amount,d.shopping_general_max_maturity_months from live_campaigns c join live_standard_product_details d on d.product_id=c.id where c.bank_name='Kuveyt Türk' and d.product_name='Taksitlio Alışveriş Finansmanı' and c.is_current=1""")
    check("Taksitlio 200.000 TL / 36 ay ürün limiti korunuyor",bool(r) and r['shopping_general_limit_amount']==200000 and r['shopping_general_max_maturity_months']==36,str(dict(r) if r else None))

    # Scope guard
    bad=_one(con,"""select count(*) n from live_campaigns c join live_standard_product_details d on d.product_id=c.id where c.bank_name='Türkiye Finans' and (d.product_name like '%Ticari Hat%' or d.product_name like '%Taksitli Ticari Taşıt%') and d.scope!='bireysel' and c.is_current=1""")['n']
    check("Adında ticari geçen Türkiye Finans bireysel taşıtları scope değiştirmiyor",bad==0,f"bad={bad}")

    con.close()
    print(f"SQLite audit sonucu: PASS={passed} FAIL={failed}")
    return passed,failed


def postgres_audit() -> tuple[int,int]:
    dsn=os.getenv('POSTGRES_DSN','').strip()
    if not dsn:
        print('PostgreSQL audit: POSTGRES_DSN yok, atlandı.')
        return 0,0
    import psycopg
    pg=psycopg.connect(dsn)
    passed=failed=0
    def check(label,ok,detail=''):
        nonlocal passed,failed
        if ok: passed+=1; print(f"PASS | PG | {label}")
        else: failed+=1; print(f"FAIL | PG | {label} | {detail}")
    with pg.cursor() as cur:
        cur.execute('SET search_path TO bansa, public')

        cur.execute("select count(*) from product_pricing_tiers where value_type is null or trim(value_type)='' or source_type is null or trim(source_type)=''")
        check('Tüm pricing tier satırlarında evidence metadata',cur.fetchone()[0]==0)
        cur.execute("select count(*) from finance_fact_evidence where value_type is null or trim(value_type)='' or source_type is null or trim(source_type)=''")
        check('finance_fact_evidence metadata eksiksiz',cur.fetchone()[0]==0)
        cur.execute("select count(*) from finance_fact_evidence")
        check('finance_fact_evidence dolu',cur.fetchone()[0]>0)

        cur.execute("""select count(*) from product_pricing_tiers p join standard_products s on s.id=p.product_id join banks b on b.id=s.bank_id where b.name='Kuveyt Türk' and p.profit_share_rate in (4.82,4.52) and s.product_name in ('Eğitim Finansmanı','Hac-Umre Finansmanı','Seyahat Finansmanı','Tekne Tüketici Finansmanı','Alışveriş Finansmanı') and p.value_type!='example'""")
        check('Kuveyt 4,82/4,52 örnek oranları headline sınıfında değil',cur.fetchone()[0]==0)

        cur.execute("""select count(*) from product_pricing_tiers p join standard_products s on s.id=p.product_id join banks b on b.id=s.bank_id where b.name='Türkiye Finans' and (s.product_name like 'Arsa Finansmanı%' or s.product_name like 'İş yeri Finansmanı%' or s.product_name like 'İş Yeri Finansmanı%' or s.product_name like 'Taksitli Ticari Taşıt%' or s.product_name like 'Ticari Hat / Ticari Plaka%' or s.product_name like 'Konut Finansmanı%' or s.product_name like 'Dijital İhtiyaç Finansmanı%' or s.product_name like 'Trendyol Alışveriş Finansmanı%') and (p.value_type!='conditional_pricing' or p.conditions is null or trim(p.conditions)='')""")
        check('Türkiye Finans koşullu fiyatlama evidence metadata',cur.fetchone()[0]==0)

        cur.execute("""select s.id from standard_products s join banks b on b.id=s.bank_id where b.name='Türkiye Finans' and s.product_name like 'Dijital İhtiyaç Finansmanı%' and s.is_current=true limit 1""")
        row=cur.fetchone()
        if row:
            pid=row[0]
            cur.execute("select min_amount,max_amount,max_maturity_months from product_amount_maturity_rules where product_id=%s order by coalesce(min_amount,-1)",(pid,))
            sig=[(float(a) if a is not None else None,float(b) if b is not None else None,int(m)) for a,b,m in cur.fetchall()]
            check('Türkiye Finans Dijital İhtiyaç 3 doğru vade bandı',sig==[(None,125000.0,36),(125000.0,250000.0,24),(250000.0,None,12)],str(sig))
        else:
            check('Türkiye Finans Dijital İhtiyaç bulundu',False)

        cur.execute("""select s.id,s.minimum_financing_amount,s.maximum_financing_amount,s.maximum_maturity_months from standard_products s join banks b on b.id=s.bank_id where b.name='Hayat Finans' and s.product_name='Bana Bunu Al' and s.is_current=true limit 1""")
        row=cur.fetchone()
        if row:
            pid,low,high,months=row
            ok=(float(low)==500.0 and float(high)==50000.0 and int(months)==18)
            check('Hayat Bana Bunu Al 500-50.000 TL / 18 ay',ok,str(row))
            cur.execute("select count(*) from product_amount_maturity_rules where product_id=%s",(pid,))
            check('Bana Bunu Al genel 125/250 bin vade bantlarını taşımıyor',cur.fetchone()[0]==0)
        else:
            check('Hayat Bana Bunu Al bulundu',False)

        cur.execute("""select s.id,s.vehicle_age_rules_text from standard_products s join banks b on b.id=s.bank_id where b.name='Dünya Katılım' and s.product_name='Araç Finansmanı' and s.is_current=true limit 1""")
        row=cur.fetchone()
        if row:
            pid,age_text=row
            cur.execute("select max_maturity_months from product_amount_maturity_rules where product_id=%s order by coalesce(min_amount,-1)",(pid,))
            vals=[int(x[0]) for x in cur.fetchall()]
            check('Dünya Araç 4 değer/vade bandı',vals==[48,36,24,12],str(vals))
            check('Dünya Araç ikinci el azami 12 yaş bilgisi','12 yaşa kadar' in str(age_text or ''),str(age_text))
        else:
            check('Dünya Araç Finansmanı bulundu',False)

        cur.execute("""select s.id from standard_products s join banks b on b.id=s.bank_id where b.name='Albaraka Türk' and s.product_name='Togg Finansmanı' and s.is_current=true limit 1""")
        row=cur.fetchone()
        if row:
            cur.execute("select financing_amount,value_type,conditions from product_pricing_tiers where product_id=%s",(row[0],))
            vals=cur.fetchall()
            check('Albaraka TOGG 6 model/tutar/vade pricing tier korunuyor',len(vals)==6 and all(x[0] is not None and x[1]=='conditional_pricing' and x[2] for x in vals),f'rows={len(vals)}')
        else:
            check('Albaraka TOGG bulundu',False)

        cur.execute("""select s.id,s.maximum_maturity_months,s.profit_share_rate,s.profit_share_rate_text from standard_products s join banks b on b.id=s.bank_id where b.name='Albaraka Türk' and s.product_name='2B Arazi Finansmanı' and s.is_current=true limit 1""")
        row=cur.fetchone()
        if row:
            pid,months,rate,rate_text=row
            check('Albaraka 2B 60 ay ve sayısal olmayan güncel fiyatlama',int(months)==60 and rate is None and 'Resmî fiyatlama' in str(rate_text or ''),str(row))
            cur.execute("select fee_type,waived from product_fee_rules where product_id=%s",(pid,))
            fees={k:bool(v) for k,v in cur.fetchall()}
            check('Albaraka 2B ekspertiz/ipotek ücretleri alınmıyor',fees.get('appraisal') is True and fees.get('mortgage_establishment') is True,str(fees))
        else:
            check('Albaraka 2B bulundu',False)

        cur.execute("""select s.id from standard_products s join banks b on b.id=s.bank_id where b.name='Kuveyt Türk' and s.product_name='Çatı GES Finansmanı' and s.scope='bireysel' and s.is_current=true limit 1""")
        row=cur.fetchone()
        if row:
            cur.execute("select feature_value from product_features where product_id=%s and feature_key='comparison_subtype'",(row[0],))
            f=cur.fetchone()
            check('Çatı GES alt türü Sürdürülebilir / Enerji',bool(f) and f[0]=='Sürdürülebilir / Enerji',str(f))
        else:
            check('Kuveyt Çatı GES bulundu',False)

        cur.execute("""select s.id from standard_products s join banks b on b.id=s.bank_id where b.name='Kuveyt Türk' and s.product_name='LC Waikiki Alışveriş Finansmanı' and s.is_current=true limit 1""")
        row=cur.fetchone()
        if row:
            cur.execute("select max_amount,max_maturity_months,max_installments,interest_free from product_offer_rules where product_id=%s",(row[0],))
            o=cur.fetchone()
            check('LC Waikiki 5.000 TL / 3 ay / vade farksız',bool(o) and float(o[0])==5000 and int(o[1])==3 and int(o[2])==3 and bool(o[3]),str(o))
        else:
            check('LC Waikiki Alışveriş Finansmanı bulundu',False)

        cur.execute("""select s.shopping_general_limit_amount,s.shopping_general_max_maturity_months from standard_products s join banks b on b.id=s.bank_id where b.name='Kuveyt Türk' and s.product_name='Taksitlio Alışveriş Finansmanı' and s.is_current=true limit 1""")
        row=cur.fetchone()
        check('Taksitlio 200.000 TL / 36 ay ürün limiti',bool(row) and float(row[0])==200000 and int(row[1])==36,str(row))

        cur.execute("""select count(*) from standard_products s join banks b on b.id=s.bank_id where b.name='Türkiye Finans' and (s.product_name like '%Ticari Hat%' or s.product_name like '%Taksitli Ticari Taşıt%') and s.scope!='bireysel' and s.is_current=true""")
        check('Adında ticari geçen Türkiye Finans bireysel taşıtları scope değiştirmiyor',cur.fetchone()[0]==0)

    pg.close(); print(f"PostgreSQL audit sonucu: PASS={passed} FAIL={failed}")
    return passed,failed


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--db',type=Path,default=DEFAULT_DB); args=parser.parse_args()
    _,sf=sqlite_audit(args.db); _,pf=postgres_audit()
    return 1 if sf or pf else 0

if __name__=='__main__': raise SystemExit(main())
