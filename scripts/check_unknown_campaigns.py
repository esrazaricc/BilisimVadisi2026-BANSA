import sqlite3

connection = sqlite3.connect("data/campaigns.db")

rows = connection.execute(
    """
    SELECT
        title,
        source_url,
        start_date,
        end_date,
        listing_status,
        fetch_status
    FROM live_campaigns
    WHERE bank_name = ?
      AND current_status = ?
    """,
    ("Albaraka Türk", "unknown"),
).fetchall()

print("Unknown kampanya sayısı:", len(rows))

for row in rows:
    print("\nBaşlık:", row[0])
    print("URL:", row[1])
    print("Başlangıç:", row[2])
    print("Bitiş:", row[3])
    print("Liste durumu:", row[4])
    print("Çekim durumu:", row[5])

connection.close()
