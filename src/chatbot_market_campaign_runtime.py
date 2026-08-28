# BANSA_LIVE_MARKET_CAMPAIGN_RUNTIME_V1

from __future__ import annotations

from datetime import date
from pathlib import Path
import re
import sqlite3
import unicodedata

from src.source_link_resolver import resolve_campaign_detail_url


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_DB = (
    ROOT
    / "data"
    / "campaigns.db"
)


def _norm(
    value,
):

    text = str(
        value
        or ""
    ).strip().casefold()

    text = (
        text
        .replace("\u0131", "i")
        .replace("\u015f", "s")
        .replace("\u011f", "g")
        .replace("\u00fc", "u")
        .replace("\u00f6", "o")
        .replace("\u00e7", "c")
    )

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(
            char
        )
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def _parse_date(
    value,
):

    raw = str(
        value
        or ""
    ).strip()

    if not raw:
        return None

    try:

        return date.fromisoformat(
            raw[:10]
        )

    except Exception:

        return None


def _today():

    return date.today()


def _is_current_campaign(
    row,
    *,
    today=None,
):

    today = (
        today
        or _today()
    )

    if (
        _norm(
            row[
                "current_status"
            ]
        )
        !=
        "active"
    ):
        return False

    if (
        _norm(
            row[
                "fetch_status"
            ]
        )
        not in {
            "ok",
            "success",
        }
    ):
        return False

    try:

        if int(
            row[
                "is_current"
            ]
            or 0
        ) != 1:
            return False

    except Exception:

        return False

    if (
        _norm(
            row[
                "record_kind"
            ]
        )
        !=
        "campaign"
    ):
        return False

    start = _parse_date(
        row[
            "start_date"
        ]
    )

    end = _parse_date(
        row[
            "end_date"
        ]
    )

    if (
        start is not None
        and
        start > today
    ):
        return False

    if (
        end is not None
        and
        end < today
    ):
        return False

    return True


def _is_strict_market_topic(
    *,
    title,
    source_url,
):

    # IMPORTANT:
    #
    # Do NOT search clean_text here.
    #
    # Some bank pages contain navigation text
    # such as "market", "alisveris" or category
    # lists even when the actual campaign is
    # unrelated.
    text = _norm(
        (
            str(
                title
                or ""
            )
            + " "
            + str(
                source_url
                or ""
            )
        )
    )

    if not text:
        return False

    # "Yapi Market" is a home-improvement
    # merchant, not grocery/food market intent.
    exclusions = (
        "yapi market",
        "yapi-markette",
        "yapi-marketi",
    )

    if any(
        value in text
        for value in exclusions
    ):
        return False

    strong = (
        "market ve gida",
        "market-ve-gida",
        "gida harcama",
        "gida-harcama",
        "supermarket",
        "super market",
        "bakkal",
        "kuruyemis",
    )

    if any(
        value in text
        for value in strong
    ):
        return True

    # Standalone "market" in the title/URL is
    # accepted after home-improvement exclusions.
    return bool(
        re.search(
            r"(?<![a-z0-9])market(?![a-z0-9])",
            text,
        )
    )


def _connect(
    db_path=None,
):

    path = Path(
        db_path
        or DEFAULT_DB
    )

    if not path.exists():

        raise FileNotFoundError(
            str(path)
        )

    connection = sqlite3.connect(
        str(path)
    )

    connection.row_factory = (
        sqlite3.Row
    )

    return connection


def bank_names(
    db_path=None,
):

    with _connect(
        db_path
    ) as conn:

        rows = conn.execute(
            """
            SELECT DISTINCT bank_name
            FROM live_campaigns
            WHERE bank_name IS NOT NULL
              AND TRIM(bank_name) <> ''
            ORDER BY bank_name
            """
        ).fetchall()

    return tuple(
        str(
            row[
                "bank_name"
            ]
        ).strip()
        for row in rows
    )


def detect_banks(
    question,
    *,
    db_path=None,
):

    text = _norm(
        question
    )

    found = []

    aliases = {
        "T.O.M. Kat\u0131l\u0131m":
            (
                "t.o.m. katilim",
                "tom katilim",
                "tom bank",
            ),
    }

    for bank in bank_names(
        db_path
    ):

        candidates = [
            _norm(
                bank
            )
        ]

        candidates.extend(
            _norm(
                alias
            )
            for alias in aliases.get(
                bank,
                ()
            )
        )

        if any(
            candidate
            and
            candidate in text

            for candidate in candidates
        ):

            found.append(
                bank
            )

    return tuple(
        found
    )


def is_market_question(
    question,
):

    text = _norm(
        question
    )

    has_campaign = any(
        value in text
        for value in (
            "kampanya",
            "kampanyasi",
            "kampanyalari",
        )
    )

    has_market = any(
        value in text
        for value in (
            "market",
            "gida",
            "supermarket",
            "bakkal",
            "kuruyemis",
        )
    )

    return (
        has_campaign
        and
        has_market
    )


def is_compare_question(
    question,
):

    text = _norm(
        question
    )

    return any(
        value in text
        for value in (
            "karsilastir",
            "karsilastirma",
            "hangisi",
        )
    )


def list_market_campaigns(
    bank_name,
    *,
    db_path=None,
    today=None,
    comparison_only=False,
):

    with _connect(
        db_path
    ) as conn:

        rows = conn.execute(
            """
            SELECT
                id,
                bank_name,
                source_url,
                source_group,
                title,
                clean_text,
                start_date,
                end_date,
                current_status,
                listing_status,
                fetch_status,
                is_current,
                record_kind,
                campaign_category,
                comparison_eligible
            FROM live_campaigns
            WHERE bank_name = ?
            ORDER BY
                COALESCE(end_date, '9999-12-31') DESC,
                id ASC
            """,
            (
                bank_name,
            ),
        ).fetchall()

    result = []

    for row in rows:

        if not _is_current_campaign(
            row,
            today=today,
        ):
            continue

        if comparison_only:

            try:

                if int(
                    row[
                        "comparison_eligible"
                    ]
                    or 0
                ) != 1:
                    continue

            except Exception:

                continue

        if not _is_strict_market_topic(
            title=row[
                "title"
            ],
            source_url=row[
                "source_url"
            ],
        ):
            continue

        result.append(
            dict(
                row
            )
        )

    return tuple(
        result
    )


def _benefit_summary(
    campaign,
):

    text = _norm(
        campaign.get(
            "clean_text"
        )
    )

    pieces = []

    min_match = re.search(
        r"(\d[\d.]*)\s*tl\s+ve\s+uzeri",
        text,
    )

    rate_match = re.search(
        r"ekstra\s*%?\s*(\d+(?:[.,]\d+)?)",
        text,
    )

    max_mil_match = re.search(
        r"aylik\s+maksimum\s+(\d[\d.]*)\s*mil",
        text,
    )

    if min_match:

        pieces.append(
            min_match.group(
                1
            )
            + " TL ve \u00fczeri harcama"
        )

    if rate_match:

        pieces.append(
            "ekstra %"
            + rate_match.group(
                1
            ).replace(
                ".",
                ",",
            )
        )

    if max_mil_match:

        pieces.append(
            "ayl\u0131k en fazla "
            + max_mil_match.group(
                1
            )
            + " Mil"
        )

    return "; ".join(
        pieces
    )


def _period(
    campaign,
):

    start = str(
        campaign.get(
            "start_date"
        )
        or ""
    ).strip()

    end = str(
        campaign.get(
            "end_date"
        )
        or ""
    ).strip()

    if start and end:

        return (
            start
            + " - "
            + end
        )

    if end:

        return (
            end
            + " tarihine kadar"
        )

    return ""


def _campaign_block(
    campaign,
):

    lines = [
        (
            "- **"
            + str(
                campaign.get(
                    "title"
                )
                or "Kampanya"
            )
            + "**"
        )
    ]

    benefit = _benefit_summary(
        campaign
    )

    if benefit:

        lines.append(
            "  - Avantaj: "
            + benefit
        )

    period = _period(
        campaign
    )

    if period:

        lines.append(
            "  - Ge\u00e7erlilik: "
            + period
        )

    source = resolve_campaign_detail_url(
        campaign.get("bank_name"),
        campaign.get("title") or campaign.get("campaign_name"),
        campaign.get("source_url"),
    )

    if source:

        lines.append(
            "  - Kaynak: "
            + source
        )

    return "\n".join(
        lines
    )


def answer_market_question(
    question,
    *,
    db_path=None,
    today=None,
):

    if not is_market_question(
        question
    ):

        return None

    banks = detect_banks(
        question,
        db_path=db_path,
    )

    if not banks:

        return None

    compare = (
        is_compare_question(
            question
        )
        and
        len(
            banks
        )
        >= 2
    )

    by_bank = {}

    for bank in banks:

        by_bank[
            bank
        ] = list_market_campaigns(
            bank,
            db_path=db_path,
            today=today,
            comparison_only=compare,
        )

    if not compare:

        bank = banks[0]

        campaigns = (
            by_bank[
                bank
            ]
        )

        if not campaigns:

            return {
                "route":
                    "campaign_rag",

                "status":
                    "NO_MATCH",

                "banks":
                    banks,

                "campaigns":
                    by_bank,

                "text":
                    (
                        bank
                        + " taraf\u0131nda bug\u00fcn i\u00e7in "
                        + "market ve g\u0131da harcamalar\u0131na "
                        + "y\u00f6nelik aktif bir kampanya "
                        + "g\u00f6remiyorum."
                    ),
            }

        blocks = "\n".join(
            _campaign_block(
                campaign
            )
            for campaign in campaigns
        )

        return {
            "route":
                "campaign_rag",

            "status":
                "FOUND",

            "banks":
                banks,

            "campaigns":
                by_bank,

            "text":
                (
                    bank
                    + " taraf\u0131nda \u015fu an market ve g\u0131da "
                    + "harcamalar\u0131na y\u00f6nelik aktif "
                    + "kampanyalar var:\n\n"
                    + blocks
                ),
        }

    lines = [
        (
            "Market ve g\u0131da kampanyalar\u0131na "
            "bakt\u0131\u011f\u0131mda durum \u015f\u00f6yle:"
        )
    ]

    found_banks = []

    missing_banks = []

    for bank in banks:

        campaigns = (
            by_bank[
                bank
            ]
        )

        lines.append(
            ""
        )

        if not campaigns:

            missing_banks.append(
                bank
            )

            lines.append(
                (
                    bank
                    + " taraf\u0131nda ise ayn\u0131 kapsamda "
                    + "aktif bir market/g\u0131da kampanyas\u0131 "
                    + "g\u00f6remiyorum."
                )
            )

            continue

        found_banks.append(
            bank
        )

        lines.append(
            (
                bank
                + " taraf\u0131nda aktif "
                + (
                    "kampanya var:"
                    if len(campaigns) == 1
                    else "kampanyalar var:"
                )
            )
        )

        for campaign in campaigns:

            lines.append(
                _campaign_block(
                    campaign
                )
            )

    lines.append(
        ""
    )

    if (
        found_banks
        and
        missing_banks
    ):

        lines.append(
            (
                "Bu nedenle mevcut aktif kampanyalara g\u00f6re "
                "market/g\u0131da taraf\u0131nda avantaj sunan taraf "
                + ", ".join(
                    found_banks
                )
                + " g\u00f6r\u00fcn\u00fcyor."
            )
        )

    elif len(
        found_banks
    ) >= 2:

        lines.append(
            (
                "Her iki bankada da aktif kampanya var. "
                "Hangisinin daha avantajl\u0131 oldu\u011fu, "
                "harcama tutar\u0131na ve kampanya ko\u015fullar\u0131na "
                "g\u00f6re de\u011fi\u015febilir."
            )
        )

    else:

        lines.append(
            (
                "Se\u00e7ti\u011fin bankalarda bug\u00fcn i\u00e7in "
                "aktif bir market/g\u0131da kampanyas\u0131 "
                "g\u00f6remiyorum."
            )
        )

    return {
        "route":
            "campaign_compare",

        "status":
            (
                "FOUND"
                if found_banks
                else
                "NO_MATCH"
            ),

        "banks":
            banks,

        "campaigns":
            by_bank,

        "text":
            "\n".join(
                lines
            ),
    }
