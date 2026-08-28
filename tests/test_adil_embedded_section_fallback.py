from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "scan_standard_products.py"
spec = spec_from_file_location("scan_standard_products_hotfix", MODULE_PATH)
module = module_from_spec(spec)
spec.loader.exec_module(module)


def test_adil_text_block_fallback_separates_individual_and_commercial():
    # Adil'in kamuya açık Ürün ve Hizmetler sayfasındaki içerik sırasını
    # temsil eder; ürün adları bağımsız heading olmak zorunda değildir.
    html = """
    <html><body>
      <div>Özel Cari Hesap Özel cari hesap açıklaması.</div>
      <div>Ticari Finansman İşletmelerin mal ve hizmet alımlarına yönelik finansman ihtiyaçları faizsiz yöntemlerle karşılanır.</div>
      <div>Katılma Hesapları Tasarruf sahipleri için hesap açıklaması.</div>
      <div>Bireysel Finansman Bireysel müşterilerimize eğitim, sağlık, tatil, ev eşyası gibi ihtiyaçlar için sağlanan faizsiz finansman türüdür.</div>
      <div>Kurumsal</div>
    </body></html>
    """
    aliases = ["Bireysel Finansman", "Ticari Finansman", "Katılma Hesapları", "Kurumsal"]

    result = module.embedded_section_html(
        html,
        product_name="Bireysel Finansman",
        aliases=["Bireysel Finansman"],
        all_product_aliases=aliases,
    )
    assert result is not None
    _, text = result
    assert "Bireysel müşterilerimize" in text
    assert "Kurumsal" not in text
    assert "Ticari Finansman" not in text

    result = module.embedded_section_html(
        html,
        product_name="Ticari Finansman",
        aliases=["Ticari Finansman"],
        all_product_aliases=aliases,
    )
    assert result is not None
    _, text = result
    assert "İşletmelerin mal ve hizmet" in text
    assert "Katılma Hesapları" not in text
    assert "Bireysel Finansman" not in text
