from src.classification.campaign_detector import classify_page
from src.extraction.rule_extractor import extract_campaign
from src.repository import save_analysis
from src.scraping.http_client import fetch_page


def analyze_text(bank_name, title, text, source_url=None, save=False):
    classification = classify_page(title, text)
    extraction = None

    if classification["is_campaign"]:
        extraction = extract_campaign(title, text)

    result = {
        "bank_name": bank_name,
        "title": title,
        "source_url": source_url,
        "raw_text": text,
        "classification": classification,
        "extraction": extraction,
    }

    if save:
        result["page_id"] = save_analysis(
            bank_name=bank_name,
            title=title,
            source_url=source_url,
            raw_text=text,
            classification=classification,
            extraction=extraction,
        )

    return result


def analyze_url(bank_name, url, save=False):
    page = fetch_page(url)
    return analyze_text(
        bank_name=bank_name,
        title=page.title,
        text=page.text,
        source_url=page.url,
        save=save,
    )
