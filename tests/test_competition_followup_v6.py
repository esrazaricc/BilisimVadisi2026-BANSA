from src.chat_followup_context import resolve_followup_question
from src.competition_fast_router import answer_fast


def test_numeric_followup_uses_immediately_previous_motorcycle_topic():
    history = [
        "Konut finansmanında Dünya Katılım ile Türkiye Finans karşılaştır.",
        "Vakıf Katılım motosiklet finansmanı hakkında bilgi ver.",
    ]
    resolution = resolve_followup_question("Peki 600 bin TL için?", history)
    assert resolution.used_context
    assert "Vakıf Katılım" in resolution.resolved_question
    assert "motosiklet finansmanı" in resolution.resolved_question
    assert "konut" not in resolution.resolved_question.casefold()
    result = answer_fast(resolution.resolved_question)
    assert result is not None
    assert "Vakıf Katılım" in result.text
    assert "Motosiklet Finansmanı" in result.text
    assert "600.000,00 TL" in result.text


def test_numeric_followup_after_two_bank_compare_preserves_compare_banks():
    history = ["Konut finansmanında Vakıf Katılım mı Türkiye Finans mı daha avantajlı?"]
    resolution = resolve_followup_question("75000 TL 24 ay", history)
    assert "Vakıf Katılım" in resolution.resolved_question
    assert "Türkiye Finans" in resolution.resolved_question
    assert "konut finansmanı" in resolution.resolved_question
