from datetime import date
import sqlite3

from src.campaign_compare import (
    compare_campaigns,
)


def _build_db(tmp_path):

    path = (
        tmp_path
        / "campaigns.db"
    )

    con = sqlite3.connect(
        path
    )

    con.executescript(
        """
        CREATE TABLE live_campaigns (
            id INTEGER PRIMARY KEY,
            clean_text TEXT,
            is_current INTEGER,
            comparison_eligible INTEGER
        );

        CREATE TABLE live_campaign_comparison (
            campaign_id INTEGER PRIMARY KEY,
            bank_name TEXT,
            campaign_name TEXT,
            campaign_category TEXT,
            start_date TEXT,
            end_date TEXT,
            source_url TEXT,
            current_status TEXT,

            reward_amount REAL,
            discount_rate REAL,
            cashback_value REAL,
            shopping_points REAL,
            campaign_installment_count REAL,
            minimum_spending REAL,
            maximum_benefit REAL,

            minimum_transaction_amount REAL,
            maximum_transaction_amount REAL,
            card_installment_count REAL,
            installment_cost_rate REAL,
            installment_cost_text TEXT
        );
        """
    )

    return path, con


def _insert(
    con,
    *,
    campaign_id,
    bank,
    name,
    category="discount_campaign",
    start_date="2026-08-01",
    end_date="2026-08-31",
    reward=None,
    discount=None,
    cashback=None,
    points=None,
    installments=None,
    minimum_spending=None,
    maximum_benefit=None,
    minimum_transaction=None,
    maximum_transaction=None,
    card_installments=None,
    installment_cost=None,
    text="market campaign",
):

    con.execute(
        """
        INSERT INTO live_campaigns (
            id,
            clean_text,
            is_current,
            comparison_eligible
        )
        VALUES (?, ?, 1, 1)
        """,
        (
            campaign_id,
            text,
        ),
    )

    con.execute(
        """
        INSERT INTO live_campaign_comparison (
            campaign_id,
            bank_name,
            campaign_name,
            campaign_category,
            start_date,
            end_date,
            source_url,
            current_status,

            reward_amount,
            discount_rate,
            cashback_value,
            shopping_points,
            campaign_installment_count,
            minimum_spending,
            maximum_benefit,

            minimum_transaction_amount,
            maximum_transaction_amount,
            card_installment_count,
            installment_cost_rate,
            installment_cost_text
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, 'active',
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?
        )
        """,
        (
            campaign_id,
            bank,
            name,
            category,
            start_date,
            end_date,
            "https://example.com/" + str(campaign_id),

            reward,
            discount,
            cashback,
            points,
            installments,
            minimum_spending,
            maximum_benefit,

            minimum_transaction,
            maximum_transaction,
            card_installments,
            installment_cost,
            None,
        ),
    )


def test_explicit_bank_lock_excludes_other_banks(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=1,
        bank="Albaraka Turk",
        name="Market A",
        reward=500,
    )

    _insert(
        con,
        campaign_id=2,
        bank="Kuveyt Turk",
        name="Market B",
        reward=600,
    )

    _insert(
        con,
        campaign_id=3,
        bank="Ziraat Katilim",
        name="Market C",
        reward=900,
    )

    con.commit()
    con.close()

    result = compare_campaigns(
        "discount_campaign",
        bank_names=(
            "Albaraka Turk",
            "Kuveyt Turk",
        ),
        as_of=date(
            2026,
            8,
            23,
        ),
        db_path=path,
    )

    assert {
        item.bank_name
        for item in result.candidates
    } == {
        "Albaraka Turk",
        "Kuveyt Turk",
    }


def test_expired_campaign_is_excluded(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=1,
        bank="Bank A",
        name="Expired",
        end_date="2026-08-01",
        reward=999,
    )

    _insert(
        con,
        campaign_id=2,
        bank="Bank B",
        name="Active",
        end_date="2026-08-31",
        reward=500,
    )

    con.commit()
    con.close()

    result = compare_campaigns(
        "discount_campaign",
        as_of=date(
            2026,
            8,
            23,
        ),
        db_path=path,
    )

    assert [
        item.campaign_id
        for item in result.candidates
    ] == [2]


def test_criterion_winner_requires_complete_coverage(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=1,
        bank="Bank A",
        name="A",
        reward=500,
    )

    _insert(
        con,
        campaign_id=2,
        bank="Bank B",
        name="B",
        reward=None,
    )

    con.commit()
    con.close()

    result = compare_campaigns(
        "discount_campaign",
        as_of=date(
            2026,
            8,
            23,
        ),
        db_path=path,
    )

    assert "reward_amount" not in {
        item.criterion
        for item in result.criterion_winners
    }


def test_effective_benefit_can_rank_same_spend(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=1,
        bank="Bank A",
        name="Ten Percent",
        discount=10,
        minimum_spending=1000,
        maximum_benefit=1000,
    )

    _insert(
        con,
        campaign_id=2,
        bank="Bank B",
        name="Fixed Reward",
        reward=300,
        minimum_spending=1000,
        maximum_benefit=300,
    )

    con.commit()
    con.close()

    result = compare_campaigns(
        "discount_campaign",
        spend_amount=5000,
        as_of=date(
            2026,
            8,
            23,
        ),
        db_path=path,
    )

    assert (
        result.may_claim_overall_winner
        is True
    )

    assert (
        result.overall_winner_campaign_ids
        == (1,)
    )


def test_points_are_not_assumed_to_equal_tl(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=1,
        bank="Bank A",
        name="Money Reward",
        category="points_campaign",
        reward=500,
    )

    _insert(
        con,
        campaign_id=2,
        bank="Bank B",
        name="Points Reward",
        category="points_campaign",
        points=1000,
    )

    con.commit()
    con.close()

    result = compare_campaigns(
        "points_campaign",
        spend_amount=5000,
        as_of=date(
            2026,
            8,
            23,
        ),
        db_path=path,
    )

    assert len(
        result.candidates
    ) == 2

    assert (
        result.may_claim_overall_winner
        is False
    )

    assert (
        "overall_ranking_blocked_incomplete_monetary_benefit"
        in result.reasons
    )


def test_card_campaign_has_no_forced_overall_winner(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=1,
        bank="Bank A",
        name="Six Installments",
        category="card_campaign",
        card_installments=6,
        installment_cost=0,
    )

    _insert(
        con,
        campaign_id=2,
        bank="Bank B",
        name="Nine Installments",
        category="card_campaign",
        card_installments=9,
        installment_cost=0,
    )

    con.commit()
    con.close()

    result = compare_campaigns(
        "card_campaign",
        spend_amount=5000,
        as_of=date(
            2026,
            8,
            23,
        ),
        db_path=path,
    )

    assert (
        result.may_claim_overall_winner
        is False
    )

    installment = next(
        item
        for item in result.criterion_winners
        if item.criterion
        == "installment_count"
    )

    assert (
        installment.campaign_ids
        == (2,)
    )



def test_topic_filter_does_not_use_noisy_body(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=101,
        bank="Bank A",
        name="Market Bonus Campaign",
        reward=500,
        text="official market benefit",
    )

    _insert(
        con,
        campaign_id=102,
        bank="Bank B",
        name="Vehicle Rental Discount",
        reward=800,
        text=(
            "footer navigation market "
            "education travel campaign"
        ),
    )

    con.commit()
    con.close()

    result = compare_campaigns(
        "discount_campaign",
        question="market",
        as_of=date(
            2026,
            8,
            23,
        ),
        db_path=path,
    )

    assert [
        item.campaign_id
        for item in result.candidates
    ] == [101]

    assert (
        "topic_filter_title_url_lock"
        in result.reasons
    )


def test_education_alias_matches_school_not_health(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=201,
        bank="Bank A",
        name="Egitim Harcamalarina 6 Taksit",
        category="card_campaign",
        card_installments=6,
    )

    _insert(
        con,
        campaign_id=202,
        bank="Bank B",
        name="Ozel Okul Odemelerine 10 Taksit",
        category="card_campaign",
        card_installments=10,
    )

    _insert(
        con,
        campaign_id=203,
        bank="Bank C",
        name="Saglik Harcamalarina 12 Taksit",
        category="card_campaign",
        card_installments=12,
        text="footer egitim navigation",
    )

    con.commit()
    con.close()

    result = compare_campaigns(
        "card_campaign",
        question="egitim",
        as_of=date(
            2026,
            8,
            23,
        ),
        db_path=path,
    )

    assert {
        item.campaign_id
        for item in result.candidates
    } == {
        201,
        202,
    }


def test_no_primary_topic_match_returns_no_candidates(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=301,
        bank="Bank A",
        name="Vehicle Rental Campaign",
        reward=500,
        text="market market market",
    )

    con.commit()
    con.close()

    result = compare_campaigns(
        "discount_campaign",
        question="market",
        as_of=date(
            2026,
            8,
            23,
        ),
        db_path=path,
    )

    assert (
        result.candidates
        == ()
    )

    assert (
        "topic_filter_no_primary_match"
        in result.reasons
    )


def test_explicit_bank_names_are_not_topic_terms(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=401,
        bank="Albaraka Turk",
        name="Egitim Harcamalarina 6 Taksit",
        category="card_campaign",
        card_installments=6,
    )

    _insert(
        con,
        campaign_id=402,
        bank="Kuveyt Turk",
        name="Egitim Harcamalarina 5 Taksit",
        category="card_campaign",
        card_installments=5,
    )

    con.commit()
    con.close()

    result = compare_campaigns(
        "card_campaign",
        bank_names=(
            "Albaraka Turk",
            "Kuveyt Turk",
        ),
        question=(
            "Albaraka Turk ve Kuveyt Turk "
            "egitim kampanyalarini karsilastir"
        ),
        as_of=date(
            2026,
            8,
            23,
        ),
        db_path=path,
    )

    assert {
        item.campaign_id
        for item in result.candidates
    } == {
        401,
        402,
    }



def test_alias_density_does_not_eliminate_other_valid_campaigns(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=501,
        bank="Bank A",
        name="Egitim Harcamalarina 6 Taksit",
        category="card_campaign",
        card_installments=6,
    )

    _insert(
        con,
        campaign_id=502,
        bank="Bank B",
        name="Egitime Ozel Taksitli POS",
        category="card_campaign",
        card_installments=10,
    )

    _insert(
        con,
        campaign_id=503,
        bank="Bank C",
        name="Ozel Okul Odemelerine 9 Taksit",
        category="card_campaign",
        card_installments=9,
    )

    con.commit()
    con.close()

    result = compare_campaigns(
        "card_campaign",
        question="egitim",
        as_of=date(
            2026,
            8,
            23,
        ),
        db_path=path,
    )

    assert {
        item.campaign_id
        for item in result.candidates
    } == {
        501,
        502,
        503,
    }


def test_url_only_valid_topic_is_not_removed_by_stronger_title(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=601,
        bank="Bank A",
        name="Egitim Harcamalarina Taksit",
        category="card_campaign",
        card_installments=6,
    )

    _insert(
        con,
        campaign_id=602,
        bank="Bank B",
        name="Kampanyaya Katilim Adimlari",
        category="card_campaign",
        card_installments=4,
    )

    con.execute(
        """
        UPDATE live_campaign_comparison
        SET source_url =
            'https://example.com/kirtasiye-kampanyasi'
        WHERE campaign_id = 602
        """
    )

    con.commit()
    con.close()

    result = compare_campaigns(
        "card_campaign",
        question="egitim",
        as_of=date(
            2026,
            8,
            23,
        ),
        db_path=path,
    )

    assert {
        item.campaign_id
        for item in result.candidates
    } == {
        601,
        602,
    }


def test_plain_market_does_not_match_hardware_market(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=701,
        bank="Bank A",
        name="Market Alisverislerine 500 TL Hediye",
        category="points_campaign",
        reward=500,
        points=500,
    )

    _insert(
        con,
        campaign_id=702,
        bank="Bank B",
        name="Mobilya Dekorasyon ve Yapi Marketi Kampanyasi",
        category="points_campaign",
        reward=1000,
        points=1000,
    )

    con.commit()
    con.close()

    result = compare_campaigns(
        "points_campaign",
        question="market",
        as_of=date(
            2026,
            8,
            23,
        ),
        db_path=path,
    )

    assert [
        item.campaign_id
        for item in result.candidates
    ] == [701]


def test_yapi_market_query_can_match_hardware_market(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=801,
        bank="Bank A",
        name="Mobilya Dekorasyon ve Yapi Marketi Kampanyasi",
        category="points_campaign",
        reward=1000,
        points=1000,
    )

    con.commit()
    con.close()

    result = compare_campaigns(
        "points_campaign",
        question="yapi market",
        as_of=date(
            2026,
            8,
            23,
        ),
        db_path=path,
    )

    assert [
        item.campaign_id
        for item in result.candidates
    ] == [801]

