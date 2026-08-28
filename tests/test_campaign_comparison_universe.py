from datetime import date
import sqlite3

from src.campaign_comparison_universe import (
    compare_campaign_universe,
    resolve_campaign_comparison_universe,
)


def _build_db(
    tmp_path,
):

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
    category,
    reward=None,
    discount=None,
    cashback=None,
    points=None,
    installments=None,
    minimum_spending=None,
    maximum_benefit=None,
    card_installments=None,
    installment_cost=None,
):

    con.execute(
        """
        INSERT INTO live_campaigns (
            id,
            clean_text,
            is_current,
            comparison_eligible
        )
        VALUES (
            ?,
            ?,
            1,
            1
        )
        """,
        (
            campaign_id,
            name,
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
            ?, ?, ?, ?,
            '2026-08-01',
            '2026-08-31',
            ?,
            'active',

            ?, ?, ?, ?, ?, ?, ?,

            NULL,
            NULL,
            ?,
            ?,
            NULL
        )
        """,
        (
            campaign_id,
            bank,
            name,
            category,
            (
                "https://example.com/"
                + str(campaign_id)
            ),
            reward,
            discount,
            cashback,
            points,
            installments,
            minimum_spending,
            maximum_benefit,
            card_installments,
            installment_cost,
        ),
    )


def test_universe_definitions():

    assert (
        resolve_campaign_comparison_universe(
            "shopping_benefit"
        )
        == (
            "discount_campaign",
            "points_campaign",
        )
    )

    assert (
        resolve_campaign_comparison_universe(
            "card_installment"
        )
        == (
            "card_campaign",
        )
    )


def test_shopping_universe_merges_discount_and_points(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=1,
        bank="Bank A",
        name="Market Discount",
        category="discount_campaign",
        discount=10,
    )

    _insert(
        con,
        campaign_id=2,
        bank="Bank B",
        name="Market Reward",
        category="points_campaign",
        reward=500,
        points=500,
    )

    con.commit()
    con.close()

    result = compare_campaign_universe(
        "shopping_benefit",
        question="market",
        spend_amount=5000,
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
        1,
        2,
    }


def test_topic_filter_still_excludes_unrelated_campaign(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=1,
        bank="Bank A",
        name="Market Discount",
        category="discount_campaign",
        discount=10,
    )

    _insert(
        con,
        campaign_id=2,
        bank="Bank B",
        name="Vehicle Rental Discount",
        category="discount_campaign",
        discount=50,
    )

    con.commit()
    con.close()

    result = compare_campaign_universe(
        "shopping_benefit",
        question="market",
        spend_amount=5000,
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
    ] == [1]


def test_explicit_bank_lock_applies_across_universe(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=1,
        bank="Bank A",
        name="Market Discount",
        category="discount_campaign",
        discount=10,
    )

    _insert(
        con,
        campaign_id=2,
        bank="Bank B",
        name="Market Reward",
        category="points_campaign",
        reward=700,
    )

    _insert(
        con,
        campaign_id=3,
        bank="Bank C",
        name="Market Reward C",
        category="points_campaign",
        reward=900,
    )

    con.commit()
    con.close()

    result = compare_campaign_universe(
        "shopping_benefit",
        bank_names=(
            "Bank A",
            "Bank B",
        ),
        question="market",
        spend_amount=5000,
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
        "Bank A",
        "Bank B",
    }


def test_cross_category_effective_benefit_can_rank(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=1,
        bank="Bank A",
        name="Market Ten Percent",
        category="discount_campaign",
        discount=10,
        maximum_benefit=1000,
    )

    _insert(
        con,
        campaign_id=2,
        bank="Bank B",
        name="Market Reward",
        category="points_campaign",
        reward=400,
        points=400,
        maximum_benefit=400,
    )

    con.commit()
    con.close()

    result = compare_campaign_universe(
        "shopping_benefit",
        question="market",
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


def test_points_only_candidate_blocks_monetary_winner(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=1,
        bank="Bank A",
        name="Market Reward",
        category="points_campaign",
        reward=500,
        points=500,
    )

    _insert(
        con,
        campaign_id=2,
        bank="Bank B",
        name="Market Points",
        category="points_campaign",
        points=1000,
    )

    con.commit()
    con.close()

    result = compare_campaign_universe(
        "shopping_benefit",
        question="market",
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

    assert (
        "overall_ranking_blocked_incomplete_monetary_benefit"
        in result.reasons
    )


def test_card_installment_universe_never_forces_global_winner(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=1,
        bank="Bank A",
        name="Egitim 6 Taksit",
        category="card_campaign",
        card_installments=6,
        installment_cost=0,
    )

    _insert(
        con,
        campaign_id=2,
        bank="Bank B",
        name="Okul 10 Taksit",
        category="card_campaign",
        card_installments=10,
        installment_cost=0,
    )

    con.commit()
    con.close()

    result = compare_campaign_universe(
        "card_installment",
        question="egitim",
        spend_amount=10000,
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

    assert (
        "overall_ranking_blocked_for_campaign_universe"
        in result.reasons
    )

    installment = next(
        winner
        for winner in result.criterion_winners
        if winner.criterion
        == "installment_count"
    )

    assert (
        installment.campaign_ids
        == (2,)
    )



def test_multiple_campaigns_same_bank_do_not_create_bank_winner(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=101,
        bank="Bank A",
        name="Market Reward 500",
        category="points_campaign",
        reward=500,
        points=500,
    )

    _insert(
        con,
        campaign_id=102,
        bank="Bank A",
        name="Market Reward 800",
        category="points_campaign",
        reward=800,
        points=800,
    )

    con.commit()
    con.close()

    result = compare_campaign_universe(
        "shopping_benefit",
        question="market",
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

    assert (
        "overall_ranking_requires_multiple_banks"
        in result.reasons
    )

    assert len(
        result.bank_representatives
    ) == 1

    assert (
        result.bank_representatives[
            0
        ].campaign_ids
        == (102,)
    )


def test_bank_level_ranking_uses_best_campaign_per_bank(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=201,
        bank="Bank A",
        name="Market Reward 200",
        category="points_campaign",
        reward=200,
        points=200,
    )

    _insert(
        con,
        campaign_id=202,
        bank="Bank A",
        name="Market Reward 700",
        category="points_campaign",
        reward=700,
        points=700,
    )

    _insert(
        con,
        campaign_id=203,
        bank="Bank B",
        name="Market Discount",
        category="discount_campaign",
        discount=10,
        maximum_benefit=1000,
    )

    con.commit()
    con.close()

    result = compare_campaign_universe(
        "shopping_benefit",
        question="market",
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
        result.overall_winner_bank_names
        == (
            "Bank A",
        )
    )

    assert (
        result.overall_winner_campaign_ids
        == (
            202,
        )
    )


def test_unknown_monetary_campaign_blocks_bank_level_ranking(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=301,
        bank="Bank A",
        name="Market Reward",
        category="points_campaign",
        reward=500,
        points=500,
    )

    _insert(
        con,
        campaign_id=302,
        bank="Bank A",
        name="Market Points Only",
        category="points_campaign",
        points=5000,
    )

    _insert(
        con,
        campaign_id=303,
        bank="Bank B",
        name="Market Discount",
        category="discount_campaign",
        discount=20,
    )

    con.commit()
    con.close()

    result = compare_campaign_universe(
        "shopping_benefit",
        question="market",
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

    assert (
        "overall_ranking_blocked_incomplete_monetary_benefit"
        in result.reasons
    )


def test_missing_explicit_bank_blocks_overall_bank_winner(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=401,
        bank="Bank A",
        name="Market Reward",
        category="points_campaign",
        reward=500,
    )

    _insert(
        con,
        campaign_id=402,
        bank="Bank B",
        name="Market Reward",
        category="points_campaign",
        reward=400,
    )

    con.commit()
    con.close()

    result = compare_campaign_universe(
        "shopping_benefit",
        bank_names=(
            "Bank A",
            "Bank B",
            "Bank C",
        ),
        question="market",
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

    assert (
        "overall_ranking_blocked_requested_bank_missing"
        in result.reasons
    )



def test_default_scope_excludes_business_pos_campaign(
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
        installment_cost=0,
    )

    _insert(
        con,
        campaign_id=502,
        bank="Bank B",
        name="Egitime Ozel Taksitli POS Kampanyasi",
        category="card_campaign",
        card_installments=12,
        installment_cost=0,
    )

    con.commit()
    con.close()

    result = compare_campaign_universe(
        "card_installment",
        question="egitim",
        spend_amount=10000,
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
    ] == [501]

    assert (
        "customer_scope:individual"
        in result.reasons
    )


def test_business_scope_keeps_business_campaign_only(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=601,
        bank="Bank A",
        name="Egitim Harcamalarina 6 Taksit",
        category="card_campaign",
        card_installments=6,
        installment_cost=0,
    )

    _insert(
        con,
        campaign_id=602,
        bank="Bank B",
        name="Egitime Ozel Taksitli POS Kampanyasi",
        category="card_campaign",
        card_installments=12,
        installment_cost=0,
    )

    con.commit()
    con.close()

    result = compare_campaign_universe(
        "card_installment",
        question="ticari egitim kampanyalari",
        spend_amount=10000,
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
    ] == [602]

    assert (
        "customer_scope:business"
        in result.reasons
    )


def test_business_scope_word_does_not_contaminate_topic_match(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=701,
        bank="Bank A",
        name="Egitime Ozel Taksitli POS Kampanyasi",
        category="card_campaign",
        card_installments=12,
        installment_cost=0,
    )

    con.commit()
    con.close()

    result = compare_campaign_universe(
        "card_installment",
        question="ticari egitim",
        spend_amount=10000,
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


def test_business_campaign_cannot_win_individual_installment_criterion(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=801,
        bank="Bank A",
        name="Egitim Harcamalarina 6 Taksit",
        category="card_campaign",
        card_installments=6,
        installment_cost=0,
    )

    _insert(
        con,
        campaign_id=802,
        bank="Bank B",
        name="Okul Harcamalarina 5 Taksit",
        category="card_campaign",
        card_installments=5,
        installment_cost=0,
    )

    _insert(
        con,
        campaign_id=803,
        bank="Bank C",
        name="Egitime Ozel Taksitli POS Kampanyasi",
        category="card_campaign",
        card_installments=12,
        installment_cost=0,
    )

    con.commit()
    con.close()

    result = compare_campaign_universe(
        "card_installment",
        question="egitim",
        spend_amount=10000,
        as_of=date(
            2026,
            8,
            23,
        ),
        db_path=path,
    )

    installment = next(
        winner
        for winner
        in result.criterion_winners
        if winner.criterion
        == "installment_count"
    )

    assert (
        installment.campaign_ids
        == (801,)
    )

    assert 803 not in {
        item.campaign_id
        for item in result.candidates
    }


def test_isim_icin_url_is_strong_business_signal(
    tmp_path,
):

    path, con = _build_db(
        tmp_path
    )

    _insert(
        con,
        campaign_id=901,
        bank="Bank A",
        name="Egitim Avantaji",
        category="card_campaign",
        card_installments=12,
        installment_cost=0,
    )

    con.execute(
        """
        UPDATE live_campaign_comparison
        SET source_url =
            'https://example.com/isim-icin/kart-kampanyalari/egitim'
        WHERE campaign_id = 901
        """
    )

    con.commit()
    con.close()

    individual = compare_campaign_universe(
        "card_installment",
        question="egitim",
        spend_amount=10000,
        as_of=date(
            2026,
            8,
            23,
        ),
        db_path=path,
    )

    business = compare_campaign_universe(
        "card_installment",
        question="ticari egitim",
        spend_amount=10000,
        as_of=date(
            2026,
            8,
            23,
        ),
        db_path=path,
    )

    assert (
        individual.candidates
        == ()
    )

    assert [
        item.campaign_id
        for item in business.candidates
    ] == [901]

