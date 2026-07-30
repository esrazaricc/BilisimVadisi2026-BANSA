import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from src.pipeline import analyze_text

DEMO_PAGES = [
    {
        "bank_name": "A Bankası",
        "title": "Yeni Ev Sahibi Olacaklara Özel Konut Finansmanı",
        "text": (
            "Yeni ev sahibi olmak isteyen müşterilerimize özel %1,89 kâr payı oranı "
            "ile 120 aya kadar konut finansmanı fırsatı sunulmaktadır. Kampanya "
            "kapsamında 50.000 TL'ye kadar dosya masrafı alınmamaktadır. Kampanya "
            "31 Aralık 2026 tarihine kadar geçerlidir."
        ),
    },
    {
        "bank_name": "B Bankası",
        "title": "Konut Finansmanı",
        "text": (
            "Konut finansmanında farklı ödeme seçenekleri sunulur. Gerekli belgeler ve "
            "başvuru koşulları için şubelerimize başvurabilirsiniz. Finansman hesaplama "
            "aracı üzerinden vade seçeneklerini inceleyebilirsiniz."
        ),
    },
    {
        "bank_name": "C Bankası",
        "title": "Yeni Konut Alımlarına 5.000 TL Alışveriş Çeki",
        "text": (
            "Yeni konut alımlarına özel %1,87 kâr payı oranı ile 96 ay vadeli konut "
            "finansmanı fırsatı. Kampanya kapsamında 5.000 TL değerinde alışveriş "
            "çeki verilmektedir."
        ),
    },
]


if __name__ == "__main__":
    for page in DEMO_PAGES:
        result = analyze_text(**page, save=True)
        page_type = result["classification"]["page_type"]
        print(f"{page['title']} -> {page_type}")
