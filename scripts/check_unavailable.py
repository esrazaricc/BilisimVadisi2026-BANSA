import json
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def unwrap_url(value):
    if isinstance(value, str):
        return value.strip()

    if isinstance(value, dict):
        for key in ("url", "href", "value"):
            if key in value:
                result = unwrap_url(value[key])
                if result:
                    return result

    return ""


def normalize_url(value):
    url = unwrap_url(value)

    if not url:
        return ""

    parts = urlsplit(url)

    scheme = (parts.scheme or "https").lower()
    host = parts.netloc.lower()

    if host.startswith("www."):
        host = host[4:]

    path = parts.path.rstrip("/")

    return urlunsplit(
        (
            scheme,
            host,
            path,
            "",
            "",
        )
    )


index_path = Path("data") / "campaign_page_index.json"

index_data = json.loads(
    index_path.read_text(encoding="utf-8")
)

index_urls = {
    normalize_url(item.get("url")): item
    for item in index_data
    if normalize_url(item.get("url"))
}

connection = sqlite3.connect("data/campaigns.db")
connection.row_factory = sqlite3.Row

rows = connection.execute(
    """
    SELECT
        title,
        source_url,
        fetch_status,
        current_status
    FROM live_campaigns
    WHERE bank_name = ?
      AND fetch_status != ?
    """,
    ("Albaraka Türk", "ok"),
).fetchall()

print("Detayı alınamayan kayıt:", len(rows))

for row in rows:
    normalized = normalize_url(row["source_url"])
    exists = normalized in index_urls

    print("\nBaşlık:", row["title"])
    print("URL:", row["source_url"])
    print("Çekim durumu:", row["fetch_status"])
    print("Kampanya durumu:", row["current_status"])
    print(
        "Kampanya indeksinde:",
        "VAR" if exists else "YOK",
    )

connection.close()
