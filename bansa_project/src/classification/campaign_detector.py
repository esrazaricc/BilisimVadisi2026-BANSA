import re

# Bir sayfayı sadece başlığında "kampanya" yazdığı için kampanya kabul etmiyoruz.
# Tarih, ödül, indirim, katılım koşulu gibi somut işaretleri birlikte arıyoruz.
CAMPAIGN_SIGNALS = [
    (r"kampanya\s+(?:kapsamında|koşulları|şartları|dönemi)", "Kampanya kapsamı veya koşulu belirtilmiş", 3),
    (r"kampanya\s+başlangıç\s+ve\s+bitiş", "Kampanya başlangıç ve bitiş alanı var", 3),
    (r"kampanyaya\s+(?:katıl|katılım)", "Kampanyaya katılım adımı var", 2),
    (r"kampanyadan\s+kimler\s+faydalanabilir", "Kampanyanın hedef kitlesi açıklanmış", 2),
    (r"(?:son|başvuru|geçerlilik)\s+tarihi", "Geçerlilik tarihi belirtilmiş", 3),
    (r"\b\d{1,2}[./-]\d{1,2}[./-]20\d{2}\b", "Sayısal kampanya tarihi var", 3),
    (r"\b\d{1,2}\s+(?:ocak|şubat|mart|nisan|mayıs|haziran|temmuz|ağustos|eylül|ekim|kasım|aralık)\s+20\d{2}\b", "Belirli bir tarih var", 3),
    (r"yeni\s+müşter", "Yeni müşterilere özel teklif var", 2),
    (r"(?:müşterilerimize|kart sahiplerine|size)\s+özel", "Belirli müşteri grubuna özel teklif var", 2),
    (r"%\s*\d+(?:[,.]\d+)?\s*(?:indirim|iade)", "İndirim veya iade oranı belirtilmiş", 3),
    (r"\b\d[\d.]*\s*(?:tl|₺)\s*(?:ödül|iade|çek|hediye)", "Ödül, iade veya hediye tutarı var", 3),
    (r"\b\d[\d.]*\s*(?:tl|₺)'?ye\s+varan\s+(?:world)?puan", "Puan üst sınırı belirtilmiş", 3),
    (r"\b\d[\d.]*\s*(?:tl|₺)\s+değerinde\s+(?:alışveriş\s+)?(?:çeki|hediye|puan)", "Çek veya hediye değeri belirtilmiş", 3),
    (r"(?:ücretsiz|masrafsız|vade\s+farksız)\s+(?:ekspertiz|tahsis|dosya|finansman|\d+\s+taksit)", "Masraf veya vade avantajı var", 3),
    (r"(?:ek|ilave|vade\s+farksız)\s+\d*\s*taksit", "Taksit avantajı var", 2),
    (r"özel\s+k[aâ]r\s+payı\s+oranı", "Özel kâr payı oranı belirtilmiş", 2),
]

PRODUCT_SIGNALS = [
    (r"gerekli\s+belgeler", "Gerekli belgeler bölümü var", 1),
    (r"nasıl\s+başvur", "Standart başvuru bilgisi var", 1),
    (r"finansman\s+hesaplama", "Finansman hesaplama aracı var", 2),
    (r"azami\s+vade", "Genel vade bilgisi var", 1),
    (r"araç\s+değerinin", "Taşıt finansmanı genel kuralı var", 1),
    (r"ürün\s+özellikleri", "Standart ürün özellikleri anlatılmış", 1),
]


def _calculate_score(text, rules):
    score = 0
    reasons = []

    for pattern, reason, point in rules:
        if re.search(pattern, text, re.IGNORECASE):
            score += point
            reasons.append(reason)

    return score, reasons


def classify_page(title, text):
    full_text = f"{title}\n{text}".lower()

    campaign_score, campaign_reasons = _calculate_score(full_text, CAMPAIGN_SIGNALS)
    product_score, product_reasons = _calculate_score(full_text, PRODUCT_SIGNALS)
    reasons = campaign_reasons + product_reasons

    if campaign_score >= 4 and campaign_score > product_score:
        confidence = min(0.98, 0.58 + campaign_score * 0.05)
        return {
            "page_type": "campaign",
            "is_campaign": True,
            "confidence": round(confidence, 2),
            "reasons": reasons,
            "score": campaign_score - product_score,
        }

    has_finance_content = re.search(r"finansman|k[aâ]r\s+payı|vade|taksit", full_text)
    if has_finance_content or product_score >= 2:
        if not reasons:
            reasons = ["Finansal ürün anlatımı var ancak somut kampanya işareti yok"]

        confidence = min(0.94, 0.62 + product_score * 0.04)
        return {
            "page_type": "standard_product",
            "is_campaign": False,
            "confidence": round(confidence, 2),
            "reasons": reasons,
            "score": campaign_score - product_score,
        }

    return {
        "page_type": "other",
        "is_campaign": False,
        "confidence": 0.70,
        "reasons": reasons or ["Kampanya veya finansman ürünü işareti bulunamadı"],
        "score": campaign_score - product_score,
    }
