import pandas as pd

from src.repository import get_campaigns

CAMPAIGN_TYPES = {
    "konut": "Konut Finansmanı Kampanyası",
    "taşıt": "Taşıt Finansmanı Kampanyası",
    "ihtiyaç": "İhtiyaç Finansmanı Kampanyası",
    "kart": "Kart Kampanyası",
    "puan": "Alışveriş Puanı Kampanyası",
    "yatırım": "Yatırım Ürünü Kampanyası",
}


def _apply_filters(question, campaigns):
    filtered = campaigns.copy()
    lowered_question = question.lower()

    for bank_name in campaigns["bank_name"].dropna().unique():
        if str(bank_name).lower() in lowered_question:
            filtered = filtered[filtered["bank_name"] == bank_name]
            break

    for word, campaign_type in CAMPAIGN_TYPES.items():
        if word in lowered_question:
            filtered = filtered[filtered["campaign_type"] == campaign_type]
            break

    if "aktif" in lowered_question:
        filtered = filtered[filtered["is_active"] == 1]

    return filtered


def answer_question(question):
    campaigns = get_campaigns()
    if campaigns.empty:
        return "Henüz kayıtlı kampanya yok. Önce Metin Analizi ekranından kampanya ekleyin."

    filtered = _apply_filters(question, campaigns)
    if filtered.empty:
        return "Bu ölçütlere uyan bir kampanya bulunamadı."

    lowered_question = question.lower()

    if "en yüksek" in lowered_question and "ödül" in lowered_question:
        valid = filtered.dropna(subset=["reward_amount"])
        if valid.empty:
            return "Uygun kampanyalarda ödül miktarı belirtilmemiş."

        row = valid.sort_values("reward_amount", ascending=False).iloc[0]
        return (
            f"En yüksek kayıtlı ödül {row['bank_name']} tarafından sunulan "
            f"{row['campaign_name']} kampanyasında {row['reward_amount']:,.0f} TL'dir."
        )

    if "en düşük" in lowered_question and ("kâr payı" in lowered_question or "oran" in lowered_question):
        valid = filtered.dropna(subset=["profit_share_rate"])
        if valid.empty:
            return "Uygun kampanyalarda kâr payı oranı belirtilmemiş."

        row = valid.sort_values("profit_share_rate").iloc[0]
        return (
            f"En düşük kayıtlı kâr payı oranı {row['bank_name']} tarafından sunulan "
            f"{row['campaign_name']} kampanyasında %{row['profit_share_rate']:.2f}'dir."
        )

    lines = []
    for _, row in filtered.head(5).iterrows():
        details = [row["bank_name"], row["campaign_name"], row["campaign_type"]]
        if pd.notna(row["campaign_end_date"]):
            details.append(f"bitiş: {row['campaign_end_date']}")
        lines.append("• " + " | ".join(str(item) for item in details))

    return "Eşleşen kampanyalar:\n" + "\n".join(lines)
