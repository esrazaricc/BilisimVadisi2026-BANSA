from src.conversation_state import ConversationState, resolve_followup_question
from src.competition_natural_chat import answer_natural


def test_generic_recommendation_goal_survives_family_clarification():
    state = ConversationState()
    history = []
    first_q = (
        "100 bin TL, 36 ay vadeyle bir finansman istiyorum ama aylık ödemem "
        "mümkün olduğunca düşük olsun. Bana en mantıklı seçeneği öner."
    )
    first = resolve_followup_question(first_q, history, _current_state=state)
    assert first.state is not None
    assert first.state.recommendation is True
    assert first.state.prefer_low_monthly is True

    first_answer = answer_natural(first.resolved_question)
    assert first_answer is not None
    assert "finansman türünü" in first_answer.text.casefold()

    history.append(first_q)
    second = resolve_followup_question(
        "konut finansmanı", history, _current_state=first.state
    )
    assert "en mantıklı seçeneği öner" in second.resolved_question.casefold()
    assert "aylık ödemesi mümkün olduğunca düşük" in second.resolved_question.casefold()

    second_answer = answer_natural(second.resolved_question)
    assert second_answer is not None
    assert "### BANSA önerisi" in second_answer.text
    assert "En düşük kâr payı" in second_answer.text
    assert "En düşük aylık taksit" in second_answer.text
    assert "En düşük toplam geri ödeme" in second_answer.text
    assert "ilk tercihim" in second_answer.text
