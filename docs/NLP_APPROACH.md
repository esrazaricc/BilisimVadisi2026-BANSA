# NLP / Metin İşleme Yaklaşımı

Mevcut sürümde sistemin ana bilgi çıkarım yaklaşımı **kural tabanlı NLP + metin madenciliği + alan bazlı normalizasyon** yapısıdır. Proje içinde henüz üretim akışına bağlı bir LLM yoktur; bu durum bilinçli olarak açıkça belirtilmektedir.

## Temel aşamalar

1. HTML / API / dinamik sayfa içeriğini alma.
2. Menü, footer ve tekrar eden gürültüyü temizleme.
3. Türkçe metin normalizasyonu.
4. Kampanya mı, hizmet bilgisi mi, standart ürün mü olduğunun sınıflandırılması.
5. Kâr payı, finansman tutarı, vade, taksit, tahsis ücreti, masraf, ödül, indirim, hedef kitle gibi alanların çıkarımı.
6. Format normalizasyonu (`%2,05`, `% 2.05`, `2.05 %` gibi varyasyonları aynı sayısal değere dönüştürme).
7. Ürün bazlı tutar-vade, kategori-taksit, fiyatlama ve masraf kurallarını normalize tablolara ayırma.
8. Kaynak kanıtını ve resmî URL'yi saklama.

## Ana dosyalar

- `src/processing/` - metin ön işleme
- `src/extraction/` - finansal ve karşılaştırma alanları
- `src/classification/` - kampanya sınıflandırma
- `src/finance_rule_engine.py` - standart finansman kuralları
- `src/qualitative_feature_extractor.py` - nitel özellikler
- `config/*overrides*.json` - kaynakta kanıtlanan banka/ürün guardrail'leri

## Semantik güvenlik ilkeleri

- Taksit sayısı ve finansman vadesi aynı alan değildir.
- `Vade farksız` ifadesi tek başına otomatik `%0 kâr payı` olarak yorumlanmaz.
- Kaynakta bulunmayan sayısal değer uydurulmaz.
- Kampanya ile standart ürün semantik olarak ayrı tutulur.
