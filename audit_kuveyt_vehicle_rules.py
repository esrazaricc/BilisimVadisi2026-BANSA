from __future__ import annotations
import json
from pathlib import Path
SCAN=Path("data")/"standard_products"/"kuveyt_turk.json"
def main()->int:
 data=json.loads(SCAN.read_text(encoding="utf-8"))
 rows=[r for r in data.get("products",[]) if r.get("product_family")=="Araç Finansmanı"]
 print("="*90); print("KUVEYT TÜRK — ARAÇ FİNANSMANI KURAL DENETİMİ"); print("="*90)
 for r in rows:
  print(); print("ÜRÜN :",r.get("product_name")); print("KURAL:",r.get("vehicle_finance_rules_text")); print("YAŞ  :",r.get("vehicle_age_rules_text")); print("URL  :",r.get("url"))
 return 0
if __name__=="__main__": raise SystemExit(main())
