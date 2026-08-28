from types import SimpleNamespace

from src.local_agent_answerer import (
    answer_local_agent,
    verify_agent_answer,
)


QUESTION = (
    "Kuveyt T\u00fcrk ile T\u00fcrkiye Finans'in "
    "market kampanyalarini karsilastir. "
    "5000 TL harcasam hangisi daha avantajli?"
)


VERIFIED = (
    "Kuveyt T\u00fcrk tarafinda aktif kampanya var. "
    "2.000 TL ve uzeri harcamada ekstra %5; "
    "aylik en fazla 2.000 Mil. "
    "T\u00fcrkiye Finans tarafinda ayni kapsamda "
    "aktif kampanya bulunmuyor. "
    "Kaynak: "
    "https://example.local/campaign"
)


def test_unsupported_number_is_rejected():

    ok, reasons = verify_agent_answer(
        question=QUESTION,
        verified_text=VERIFIED,
        answer=(
            "5000 TL harcamada "
            "250 Mil kazanirsiniz."
        ),
    )

    assert ok is False

    assert any(
        reason.startswith(
            "unsupported_numbers:"
        )
        for reason in reasons
    )


def test_maximum_cannot_be_recast_as_exact_gain():

    ok, reasons = verify_agent_answer(
        question=QUESTION,
        verified_text=VERIFIED,
        answer=(
            "5000 TL harcamada "
            "2.000 Mil kazanirsiniz."
        ),
    )

    assert ok is False

    assert (
        "maximum_recast_as_exact_gain:2000:mil"
        in reasons
    )


def test_maximum_qualified_statement_is_allowed():

    ok, reasons = verify_agent_answer(
        question=QUESTION,
        verified_text=VERIFIED,
        answer=(
            "Kuveyt T\u00fcrk tarafinda "
            "aylik en fazla 2.000 Mil "
            "kazanabilirsiniz. "
            "T\u00fcrkiye Finans tarafinda "
            "aktif kampanya bulunmuyor."
        ),
    )

    assert ok is True
    assert reasons == ()


def test_new_bank_is_rejected():

    ok, reasons = verify_agent_answer(
        question=QUESTION,
        verified_text=VERIFIED,
        answer=(
            "Albaraka T\u00fcrk daha avantajli."
        ),
    )

    assert ok is False

    assert any(
        reason.startswith(
            "unsupported_bank:"
        )
        for reason in reasons
    )


def test_new_url_is_rejected():

    ok, reasons = verify_agent_answer(
        question=QUESTION,
        verified_text=VERIFIED,
        answer=(
            "Kaynak: "
            "https://evil.example/test"
        ),
    )

    assert ok is False

    assert (
        "unsupported_url"
        in reasons
    )


class FakeClient:

    def __init__(
        self,
        text,
    ):
        self.text = text

    def chat(
        self,
        *args,
        **kwargs,
    ):
        return {
            "role":
                "assistant",

            "content":
                self.text,
        }


def _run_result():

    return SimpleNamespace(
        status="ok",
        tool_result=SimpleNamespace(
            data={
                "result": {
                    "text":
                        VERIFIED,
                }
            }
        ),
    )


def test_bad_generation_returns_verified_fallback():

    result = answer_local_agent(
        question=QUESTION,
        run_result=_run_result(),
        client=FakeClient(
            (
                "5000 TL harcamada "
                "2.000 Mil kazanirsiniz."
            )
        ),
    )

    assert (
        result.status
        ==
        "safe_fallback"
    )

    assert result.verified is True

    assert (
        result.fallback_used
        is True
    )

    assert (
        result.text
        ==
        VERIFIED
    )


def test_grounded_generation_is_accepted():

    result = answer_local_agent(
        question=QUESTION,
        run_result=_run_result(),
        client=FakeClient(
            (
                "Kuveyt T\u00fcrk tarafinda "
                "aylik en fazla 2.000 Mil "
                "avantaji bulunuyor. "
                "T\u00fcrkiye Finans tarafinda "
                "ayni kapsamda aktif kampanya "
                "bulunmuyor. "
                "Kaynak: "
                "https://example.local/campaign"
            )
        ),
    )

    assert (
        result.status
        ==
        "verified_model_answer"
    )

    assert result.verified is True

    assert (
        result.fallback_used
        is False
    )

def test_scaled_user_amount_is_allowed():

    ok, reasons = verify_agent_answer(
        question=(
            "200 bin TL icin "
            "36 ay hesapla."
        ),
        verified_text=(
            "Vade 36 ay."
        ),
        answer=(
            "200.000 TL icin "
            "36 ay sonucudur."
        ),
    )

    assert ok is True
    assert reasons == ()


class TruncatedFakeClient:

    def chat(
        self,
        *args,
        **kwargs,
    ):

        return {
            "role":
                "assistant",

            "content":
                "Yarim kalan cevap 32",

            "_finish_reason":
                "length",
        }


def test_truncated_generation_returns_verified_fallback():

    result = answer_local_agent(
        question=QUESTION,
        run_result=_run_result(),
        client=TruncatedFakeClient(),
    )

    assert (
        result.status
        ==
        "safe_fallback"
    )

    assert result.verified is True
    assert result.model_used is True
    assert result.fallback_used is True

    assert (
        "answer_model_truncated:length"
        in result.reasons
    )

def test_markdown_url_is_rejected_even_when_url_is_grounded():

    url = (
        "https://example.local/campaign"
    )

    ok, reasons = verify_agent_answer(
        question=(
            "Kampanyayi ozetle."
        ),
        verified_text=(
            "Kaynak: "
            + url
        ),
        answer=(
            "Kaynak: ["
            + url
            + "]("
            + url
            + ")"
        ),
    )

    assert ok is False

    assert (
        "markdown_url_not_allowed"
        in reasons
    )


def test_plain_grounded_url_is_allowed():

    url = (
        "https://example.local/campaign"
    )

    ok, reasons = verify_agent_answer(
        question=(
            "Kampanyayi ozetle."
        ),
        verified_text=(
            "Kaynak: "
            + url
        ),
        answer=(
            "Kaynak: "
            + url
        ),
    )

    assert ok is True
    assert reasons == ()

def test_answerer_sanitizes_grounded_markdown_url():

    url = (
        "https://example.local/campaign"
    )

    result = answer_local_agent(
        question=QUESTION,
        run_result=_run_result(),
        client=FakeClient(
            (
                "Kaynak: ["
                + url
                + "]("
                + url
                + ")"
            )
        ),
    )

    assert (
        result.status
        ==
        "verified_model_answer"
    )

    assert result.verified is True
    assert result.model_used is True
    assert result.fallback_used is False

    assert (
        result.text
        ==
        "Kaynak: "
        + url
    )


def test_answerer_does_not_sanitize_unsupported_markdown_url():

    bad_url = (
        "https://unsupported.example/"
    )

    result = answer_local_agent(
        question=QUESTION,
        run_result=_run_result(),
        client=FakeClient(
            (
                "Kaynak: ["
                + bad_url
                + "]("
                + bad_url
                + ")"
            )
        ),
    )

    assert (
        result.status
        ==
        "safe_fallback"
    )

    assert result.verified is True
    assert result.fallback_used is True

    assert (
        "generated_answer_rejected"
        in result.reasons
    )

def test_verifier_rejects_finance_fee_coverage_negation_flip():
    from src.local_agent_answerer import verify_agent_answer

    verified_text = (
        "Baz\u0131 adaylarda toplam \u00fccret bilgisi eksiksiz "
        "olmad\u0131\u011f\u0131 i\u00e7in genel de\u011ferlendirmede toplam "
        "geri \u00f6deme esas al\u0131nm\u0131\u015ft\u0131r."
    )

    answer = (
        "Toplam \u00fccret bilgisi eksik olmasa da, "
        "toplam geri \u00f6deme esas al\u0131nm\u0131\u015ft\u0131r."
    )

    verified, reasons = verify_agent_answer(
        question="Finansmanlar\u0131 kar\u015f\u0131la\u015ft\u0131r.",
        verified_text=verified_text,
        answer=answer,
    )

    assert verified is False
    assert (
        "finance_fee_coverage_negation_flip"
        in reasons
    )


def test_verifier_accepts_preserved_incomplete_fee_coverage():
    from src.local_agent_answerer import verify_agent_answer

    verified_text = (
        "Baz\u0131 adaylarda toplam \u00fccret bilgisi eksiksiz "
        "olmad\u0131\u011f\u0131 i\u00e7in genel de\u011ferlendirmede toplam "
        "geri \u00f6deme esas al\u0131nm\u0131\u015ft\u0131r."
    )

    answer = (
        "Baz\u0131 adaylarda toplam \u00fccret bilgisi eksiksiz "
        "olmad\u0131\u011f\u0131 i\u00e7in toplam geri \u00f6deme "
        "esas al\u0131nm\u0131\u015ft\u0131r."
    )

    verified, reasons = verify_agent_answer(
        question="Finansmanlar\u0131 kar\u015f\u0131la\u015ft\u0131r.",
        verified_text=verified_text,
        answer=answer,
    )

    assert verified is True
    assert reasons == ()

def test_verifier_rejects_omitted_finance_fee_coverage_caveat():
    from src.local_agent_answerer import verify_agent_answer

    verified_text = (
        "Bazi adaylarda toplam ucret bilgisi eksiksiz "
        "olmadigi icin genel sonucta toplam geri "
        "odeme esas alindi."
    )

    answer = (
        "Toplam geri odemesi daha dusuk olan secenek "
        "bu kriterlere gore daha mantiklidir."
    )

    verified, reasons = verify_agent_answer(
        question="Konut finansmanlarini karsilastir.",
        verified_text=verified_text,
        answer=answer,
    )

    assert verified is False

    assert (
        "finance_fee_coverage_caveat_omitted"
        in reasons
    )


def test_verifier_accepts_preserved_finance_fee_coverage_caveat():
    from src.local_agent_answerer import verify_agent_answer

    verified_text = (
        "Bazi adaylarda toplam ucret bilgisi eksiksiz "
        "olmadigi icin genel sonucta toplam geri "
        "odeme esas alindi."
    )

    answer = (
        "Bazi adaylarda toplam ucret bilgisi eksiksiz "
        "olmadigi icin sonuc toplam geri odeme "
        "uzerinden degerlendirilmistir."
    )

    verified, reasons = verify_agent_answer(
        question="Konut finansmanlarini karsilastir.",
        verified_text=verified_text,
        answer=answer,
    )

    assert verified is True
    assert reasons == ()

