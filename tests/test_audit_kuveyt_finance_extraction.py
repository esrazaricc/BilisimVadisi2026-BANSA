import sqlite3

from scripts.audit_kuveyt_finance_extraction import (
    audit_rows,
)


def test_audit_flags_missing_finance_fields():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE sample (
            id INTEGER,
            title TEXT,
            source_url TEXT,
            clean_text TEXT,
            finance_type TEXT,
            profit_share_rate_text TEXT,
            financing_amount_text TEXT,
            maturity_text TEXT,
            grace_period_months INTEGER,
            installment_count INTEGER,
            allocation_fee_status TEXT,
            expense_status TEXT,
            campaign_advantage TEXT,
            extraction_confidence REAL
        );
        """
    )

    connection.execute(
        """
        INSERT INTO sample (
            id,
            title,
            source_url,
            clean_text,
            finance_type,
            profit_share_rate_text,
            financing_amount_text,
            maturity_text,
            grace_period_months,
            installment_count,
            allocation_fee_status,
            expense_status,
            campaign_advantage,
            extraction_confidence
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            "TOGG Finansman Kampanyası",
            "https://example.com/togg",
            (
                "12 ay vadede %0 kar payı ile 750.000 TL "
                "finansman sunulur. 3 ay erteleme ve "
                "12 taksit avantajı vardır."
            ),
            "Togg Taşıt Finansmanı",
            None,
            None,
            "12 aya kadar",
            None,
            None,
            None,
            None,
            (
                "Banka koşulları değiştirme hakkına sahiptir."
            ),
            0.72,
        ),
    )

    rows = connection.execute(
        "SELECT * FROM sample"
    ).fetchall()
    result = audit_rows(rows)

    assert result["finance_campaign_count"] == 1
    assert result["review_campaign_count"] == 1

    flags = result["items"][0]["review_flags"]
    assert any("kâr payı" in flag for flag in flags)
    assert any("finansman tutarı" in flag for flag in flags)
    assert any("Ödemesiz dönem" in flag for flag in flags)
    assert any("Taksit" in flag for flag in flags)
    assert any("hukuki açıklama" in flag for flag in flags)
