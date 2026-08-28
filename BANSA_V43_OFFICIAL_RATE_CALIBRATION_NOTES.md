# BANSA V43 - Official Rate Calibration Final

Bu sürüm V42 mimarisini, kampanya UI katmanını, kart karşılaştırmasını ve chatbot akışını koruyarak yalnızca ana finansman oran katmanını kalibre eder.

## Amaç

V41/V42'de hesaplama motoru çalışıyordu; ancak bazı bankalarda kullanılan kâr payı oranları banka web sitesindeki hesaplama ekranı ile birebir aynı değildi. V43'te oranlar kullanıcı tarafından paylaşılan resmî banka hesaplama ekranı snapshotlarına göre güncellendi.

## Yeni kaynak yaklaşımı

- Kâr payı oranları artık tek tip “resmî sabit oran” gibi gösterilmez.
- Ekran görüntüsünden doğrulanan oranlar `official_calculator_snapshot_model` olarak etiketlenir.
- UI ve chatbotta kaynak türü “resmî hesaplama ekranı snapshotı” olarak görünür.
- “Hesaplama aracını aç” kullanıcı aksiyonu kullanılmaz; BANSA içeride hesaplamaya devam eder.
- Dünya Katılım için kullanıcı tarafından ayrı snapshot verilmediği için V42 kaynak modeli korunmuştur.

## Kalibre edilen oran snapshotları

### Konut

| Banka | Tutar | Vade | Kâr oranı | Aylık taksit | Toplam |
|---|---:|---:|---:|---:|---:|
| Albaraka Türk | 500.000 TL | 20 ay | %3,04 | 33.765,42 TL | 675.308,89 TL |
| Kuveyt Türk | 500.000 TL | 120 ay | %2,9900 | 15.398,82 TL | 1.847.868,29 TL |
| Türkiye Finans | 500.000 TL | 120 ay | %2,88 | 14.893,49 TL | 1.787.218,80 TL |
| Vakıf Katılım | 100.000 TL | 60 ay | %2,99 | 3.605,56 TL | 216.333,48 TL |

### Taşıt

| Banka | Tutar | Vade | Kâr oranı | Aylık taksit | Toplam |
|---|---:|---:|---:|---:|---:|
| Albaraka Türk | 267.500 TL | 12 ay | %3,55 | 29.572,47 TL | 356.407,19 TL |
| Kuveyt Türk | 500.000 TL | 48 ay | %3,3900 | 25.216,76 TL | 1.210.404,67 TL |
| Türkiye Finans | 100.000 TL | 48 ay | %3,42 | 5.074,96 TL | 243.598,08 TL |
| Vakıf Katılım | 100.000 TL | 24 ay | %3,29 | 6.746,01 TL | 161.904,12 TL |

### İhtiyaç

| Banka | Tutar | Vade | Kâr oranı | Aylık taksit | Toplam |
|---|---:|---:|---:|---:|---:|
| Albaraka Türk | 150.000 TL | 23 ay | %4,00 | 11.349,76 TL | 261.044,84 TL |
| Türkiye Finans | 100.000 TL | 36 ay | %3,80 | 5.996,94 TL | 215.889,84 TL |
| Kuveyt Türk | 500.000 TL | 12 ay | %4,0100 | 57.092,42 TL | 685.108,95 TL |
| Vakıf Katılım | 100.000 TL | 18 ay | %3,99 | 8.680,05 TL | 156.240,94 TL |

## Testler

Çalıştırılan hedefli testler:

```text
python -m compileall -q src pages
PYTHONPATH=. pytest -q \
  tests/test_v43_official_rate_calibration.py \
  tests/test_v40_internal_finance_calculation.py \
  tests/test_competition_scenario_projection_v5.py \
  tests/test_competition_fast_router.py \
  tests/test_v39_campaign_ui_refresh.py \
  tests/test_v33_card_dashboard.py \
  tests/test_v24_placeholders_and_detail_links.py
```

Sonuç: 45 passed.

## Bilinen sınır

Tam test suite içinde daha eski oran beklentilerine göre yazılmış bazı legacy testler bulunmaktadır. V43 oran kalibrasyonu bilinçli olarak bu eski beklentileri geçersiz kılar. Hedeflenen V43 oran, chatbot ve UI regresyon testleri güncellenmiş ve geçmiştir.
