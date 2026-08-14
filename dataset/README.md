# BANSA Veri Seti Snapshot'ı

Bu klasör, `data/campaigns.db` snapshot'ından üretilen yarışma veri setinin okunabilir CSV dışa aktarımlarını içerir.

Snapshot özeti (14 Ağustos 2026):

- Güncel sınıflandırılmış kampanya: **527**
- Standart finansman ürünü: **124**
- Kampanya bankaları: Albaraka Türk (104), Dünya Katılım (42), Hayat Finans (11), Kuveyt Türk (110), T.O.M. Katılım (75), Türkiye Emlak Katılım (64), Türkiye Finans (49), Ziraat Katılım (72)
- Standart ürün bankaları: Albaraka Türk (41), Dünya Katılım (10), Hayat Finans (7), Kuveyt Türk (43), Türkiye Finans (23)
- Açık sınıflandırma kontrolü: Vakıf Katılım (23)

## Dosyalar

- `campaigns.csv`: güncel kampanyalar + yapılandırılmış finansman alanları
- `campaign_texts.csv`: kaynak URL ile birlikte temizlenmiş kaynak metinleri
- `campaign_benefits.csv`: ödül/indirim/puan avantajları
- `campaign_audiences.csv`: hedef kitle bilgileri
- `campaign_installment_terms.csv`: taksit kuralları
- `standard_products.csv`: standart finansman ürünleri
- `product_*_rules.csv`: vade, kategori, fiyatlama, masraf ve özel kural tabloları
- `product_features.csv`: nitel ürün özellikleri
- `raw_standard_products/`: banka bazlı güncel standart ürün JSON çıktıları
- `manifest.json`: dosya satır sayıları

Veri, katılım bankalarının resmî web sayfalarından proje kapsamında toplanmıştır. Her kayıt mümkün olduğunda `source_url` ile kaynağa bağlanır. Banka web sayfalarının kendi içerik hakları ilgili kurumlara aittir; bu repo, yarışma kapsamında analiz ve yeniden üretilebilirlik amacıyla kaynak adreslerini ve işlenmiş veriyi sunar.

Yeniden üretmek için:

```powershell
python -X utf8 .\scripts\export_public_dataset.py
```
