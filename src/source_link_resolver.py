from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_INDEX_PATH = ROOT / "data" / "campaign_page_index.json"
CAMPAIGN_ALIAS_PATH = ROOT / "config" / "campaign_url_aliases.json"
PRODUCT_SOURCE_CONFIG_PATH = ROOT / "config" / "standard_product_sources.json"


def _norm_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().replace("ı", "i")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _canonical_url(value: object) -> str:
    return str(value or "").strip().rstrip("/")


@lru_cache(maxsize=1)
def _campaign_aliases() -> dict[str, str]:
    try:
        payload = json.loads(CAMPAIGN_ALIAS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, str] = {}
    for item in payload if isinstance(payload, list) else []:
        source = _canonical_url(item.get("source_url"))
        target = _canonical_url(item.get("target_url"))
        if source and target:
            out[source] = target
    return out


@lru_cache(maxsize=1)
def _campaign_index() -> tuple[dict[str, object], ...]:
    try:
        payload = json.loads(CAMPAIGN_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return ()
    return tuple(x for x in payload if isinstance(x, dict)) if isinstance(payload, list) else ()




@lru_cache(maxsize=1)
def _live_campaign_links() -> tuple[dict[str, str], ...]:
    db_path = ROOT / "data" / "campaigns.db"
    if not db_path.exists():
        return ()
    try:
        connection = sqlite3.connect(str(db_path))
        rows = connection.execute(
            """
            SELECT bank_name, title, source_url, current_status, is_current
            FROM live_campaigns
            WHERE record_kind = 'campaign'
            """
        ).fetchall()
        connection.close()
    except Exception:
        return ()
    return tuple(
        {
            "bank_name": str(row[0] or ""),
            "title": str(row[1] or ""),
            "url": str(row[2] or ""),
            "current_status": str(row[3] or ""),
            "is_current": str(row[4] or ""),
        }
        for row in rows
        if str(row[2] or "").strip()
    )


def _is_generic_campaign_url(url: str) -> bool:
    if not url:
        return True
    path = urlparse(url).path.rstrip("/").casefold()
    generic_suffixes = (
        "/kampanyalar",
        "/kampanya",
        "/kart-kampanyalari",
        "/campaigns",
        "/kampanyalar/sayfalar",
    )
    return any(path.endswith(suffix) for suffix in generic_suffixes)


def _title_score(left: str, right: str) -> float:
    a = _norm_text(left)
    b = _norm_text(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    aset = set(a.split())
    bset = set(b.split())
    if not aset or not bset:
        return 0.0
    intersection = len(aset & bset)
    union = len(aset | bset)
    jaccard = intersection / union if union else 0.0
    containment = intersection / min(len(aset), len(bset))
    prefix = 1.0 if a in b or b in a else 0.0
    return max(jaccard, 0.85 * containment, 0.90 * prefix)


def resolve_campaign_detail_url(bank_name: object, campaign_name: object, source_url: object) -> str:
    """Return the most specific official campaign page available locally.

    Resolution is local/offline and therefore safe for demo use.  Existing URL
    aliases are applied first.  Then the campaign detail index is searched by
    bank + title, preferring a detail page over a listing/category page.
    """
    current = _canonical_url(source_url)
    current = _campaign_aliases().get(current, current)
    bank_key = _norm_text(bank_name)
    title = str(campaign_name or "").strip()

    best_url = ""
    best_score = -1.0

    # The synchronized live-campaign table is the most current local URL
    # directory.  This also repairs older records whose source URL pointed to
    # a category/listing page.
    for item in _live_campaign_links():
        if _norm_text(item.get("bank_name")) != bank_key:
            continue
        url = _canonical_url(item.get("url"))
        if not url or _is_generic_campaign_url(url):
            continue
        score = _title_score(title, str(item.get("title") or "")) + 0.10
        if str(item.get("current_status") or "").casefold() == "active":
            score += 0.03
        if str(item.get("is_current") or "") == "1":
            score += 0.02
        if score > best_score:
            best_score = score
            best_url = url

    for item in _campaign_index():
        if _norm_text(item.get("bank_name")) != bank_key:
            continue
        url = _canonical_url(item.get("url") or item.get("requested_url"))
        if not url:
            continue
        page_type = _norm_text(item.get("page_type"))
        score = _title_score(title, str(item.get("title") or ""))
        if page_type == "campaign detail":
            score += 0.12
        if _canonical_url(item.get("url")) == current:
            score += 0.08
        if str(item.get("current_status") or "").casefold() == "active":
            score += 0.03
        if score > best_score:
            best_score = score
            best_url = url

    # A strong title match is safer than a generic/listing source URL.  If the
    # source is already a detail URL, only replace it on a very strong match.
    threshold = 0.72 if _is_generic_campaign_url(current) else 0.93
    if best_url and best_score >= threshold:
        return _campaign_aliases().get(best_url, best_url)
    return current


@lru_cache(maxsize=1)
def _product_source_config() -> tuple[dict[str, object], ...]:
    try:
        payload = json.loads(PRODUCT_SOURCE_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return ()
    banks = payload.get("banks", []) if isinstance(payload, dict) else []
    return tuple(item for item in banks if isinstance(item, dict))


def _product_path_candidates(bank_name: object, product_name: object) -> tuple[str, ...]:
    bank_key = _norm_text(bank_name)
    title = str(product_name or "").strip()
    ranked: list[tuple[float, str]] = []
    for bank in _product_source_config():
        if _norm_text(bank.get("name")) != bank_key:
            continue
        base = _canonical_url(bank.get("base_url"))
        if not base:
            continue
        for rule in bank.get("family_rules", []) or []:
            if not isinstance(rule, dict):
                continue
            for path in rule.get("exact_paths", []) or []:
                path = str(path or "").strip()
                if not path:
                    continue
                slug = path.rstrip("/").split("/")[-1].replace("-", " ")
                score = _title_score(title, slug)
                # Strong token containment is enough for names like
                # "Tamamlayıcı Konut Finansmanı" -> tamamlayici-konut-finansmani.
                if score >= 0.68:
                    ranked.append((score, base + (path if path.startswith("/") else "/" + path)))
    ranked.sort(key=lambda x: (-x[0], -len(urlparse(x[1]).path)))
    return tuple(url for _, url in ranked)


def resolve_product_detail_url(bank_name: object, product_name: object, source_url: object) -> str:
    """Keep product links on the product's own official page when one exists.

    Standard-product records already carry the discovered source URL.  This
    guard mainly prevents an accidental fallback to a bank homepage/category
    when a more specific URL is embedded in the local product JSON catalogue.
    """
    current = _canonical_url(source_url)
    bank_key = _norm_text(bank_name)
    product_key = _norm_text(product_name)
    if not bank_key or not product_key:
        return current

    best = current
    best_depth = len(urlparse(current).path.split("/")) if current else 0
    standard_dir = ROOT / "data" / "standard_products"
    for path in standard_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        records = payload if isinstance(payload, list) else payload.get("products", []) if isinstance(payload, dict) else []
        for item in records:
            if not isinstance(item, dict):
                continue
            if _norm_text(item.get("bank_name")) != bank_key:
                continue
            if _norm_text(item.get("product_name")) != product_key:
                continue
            candidate = _canonical_url(item.get("source_url") or item.get("url") or item.get("source_page"))
            if not candidate:
                continue
            depth = len([p for p in urlparse(candidate).path.split("/") if p])
            if depth > best_depth:
                best = candidate
                best_depth = depth

    # If the local product record is an embedded/category page, the source
    # discovery config may still contain a product-specific exact path. Use it
    # only on a strong product-name/slug match; never guess a URL.
    for candidate in _product_path_candidates(bank_name, product_name):
        depth = len([p for p in urlparse(candidate).path.split("/") if p])
        if depth > best_depth:
            best = candidate
            best_depth = depth
            break
    return best
