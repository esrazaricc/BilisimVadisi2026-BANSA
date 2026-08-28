# BANSA V47 — User-Facing Accuracy Final

Bu sürüm V45/V46 finansal doğruluk ve öneri mimarisini korur; kullanıcıya görünen chatbot ve karşılaştırma ekranlarındaki intent/context, metin ve tablo problemlerini düzeltir.

## Ana düzeltmeler
- Araç değeri, nakit/peşinat ve talep edilen finansman tutarı ayrı semantiklerle ele alınır.
- Aylık ödeme üst sınırı ve araç değer bandı bankaları sıralamadan önce uygunluk katmanından geçer.
- Generic finansman sorusu önceki konut/taşıt bağlamını yanlışlıkla miras almaz.
- Kampanya follow-up soruları (örn. “ne zamana kadar geçerli?”) önceki kampanya bağlamını korur.
- Kart ürünü soruları kampanya/finansman route’una düşmez; kart kataloğundan cevaplanır.
- Ticari makine/teçhizat sorularında fiyat kanıtı yoksa sahte maliyet sıralaması yapılmaz; ürün-amacı uyumu önerilir.
- Telefon alışverişi genel ihtiyaç finansmanı gibi yorumlanmaz; amaç bazlı alışveriş/telefon kuralları korunur.
- Kullanıcı “öner” dediğinde en düşük kâr payı, aylık taksit ve toplam ödeme gibi doğrulanabilir karşılaştırma ölçütleri öne alınır.
- Dashboard kullanıcı görünümünde internal `Durum`, ham `Varyant`, `Sonuç Türü`, ISO `Kontrol Tarihi`, QA `Not` gibi teknik alanlar gizlenir veya kullanıcı dostu adlara dönüştürülür.
- `0Km Sigortali / 2El Sigortali`, `Standard` gibi ham değerler kullanıcı dostu Türkçeye çevrilir.
- Campaign compare follow-up route/backend metadata sözleşmesi stabilize edildi.

## Regresyon doğrulaması
Aşağıdaki V43–V47 ve chatbot/rendering odaklı seçili regresyon paketi çalıştırıldı:

`50 passed`

Ayrıca `src`, `pages`, `scripts` ve `Ana_Sayfa.py` Python compile kontrolü geçti.
