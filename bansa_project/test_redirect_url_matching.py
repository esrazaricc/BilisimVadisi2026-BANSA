import json
from pathlib import Path

from src.database.live_campaign_sync import build_snapshot_lookup


def test_redirected_snapshot_is_found_by_requested_url(tmp_path: Path):
    snapshot_file = tmp_path / "snapshot.json"
    snapshot_file.write_text(
        json.dumps(
            {
                "bank_name": "Albaraka Türk",
                "url": (
                    "https://albaraka.com.tr/tr/kampanyalar/"
                    "detay/subesiz-umre-finansmani"
                ),
                "requested_url": (
                    "https://albaraka.com.tr/tr/kampanyalar/"
                    "detay/umre-finansmani-kampanyasi"
                ),
                "title": "Şubesiz Umre Finansmanı",
                "fetch_status": "ok",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    index_items = [
        {
            "bank_name": "Albaraka Türk",
            "url": (
                "https://albaraka.com.tr/tr/kampanyalar/"
                "detay/subesiz-umre-finansmani"
            ),
            "requested_url": (
                "https://albaraka.com.tr/tr/kampanyalar/"
                "detay/umre-finansmani-kampanyasi"
            ),
            "snapshot_file": str(snapshot_file),
        }
    ]

    lookup = build_snapshot_lookup(
        index_items,
        "Albaraka Türk",
    )

    requested = (
        "https://albaraka.com.tr/tr/kampanyalar/"
        "detay/umre-finansmani-kampanyasi"
    )
    final = (
        "https://albaraka.com.tr/tr/kampanyalar/"
        "detay/subesiz-umre-finansmani"
    )

    assert requested in lookup
    assert final in lookup
    assert lookup[requested]["title"] == "Şubesiz Umre Finansmanı"
