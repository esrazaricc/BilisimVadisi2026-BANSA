# BANSA V45 — Live Scenario Integrity

## Neden V45?
V44'te resmi hesaplama araci eslemesi eklenmis olsa da iki kritik risk kalmisti:

1. Canli calculator gecici olarak dogrulanamazsa sistem eski verified/model oranina dusebiliyor ve bu oran kullaniciya guncel gibi gorunebiliyordu.
2. Chatbotta vade belirtilmediginde her banka icin farkli historical verified vade secilebiliyor, fakat baslikta tek bir azami vade gosterilebiliyordu. Bu durum 36 aylik sonucun 120 ay basligi altinda gorunmesi gibi presentation-integrity hatasi uretebiliyordu.

V45 bu iki yolu kapatir.

## Tek senaryo resolver'i
Dashboard ve chatbot artik ayni `src/finance_user_scenario_resolver.py` politikasini kullanir.

Sirasi:

1. Resmi live calculator mapping varsa exact `amount + maturity` canli olarak sorgulanir.
2. `VERIFIED + exact-match` sonuc gelirse kullanilir.
3. Mapping var fakat canli sonuc dogrulanamazsa **eski oran/model fallback'i yasaktir**. Sayisal sonuc gosterilmez.
4. Yalniz resmi live mapping bulunmayan urunlerde mevcut verified deterministic source model kullanilabilir.

Bu nedenle dashboard ile chatbot ayni banka icin farkli rakam uretemez.

## Vade butunlugu
Kullanici vade girdiyse her sonuc tam olarak o vadeye ait olmak zorundadir.

Kullanici vade girmediyse cok-bankali senaryolarda artik banka banka farkli historical maturity secilmez. Urun grubunda en yaygin yayimlanmis azami vade tek ortak senaryo olarak secilir ve tum bankalara ayni maturity gonderilir.

Ornek: konut grubunda ortak varsayilan 120 ay ise baslikta 120 ay yazan tum sayisal sonuclar gercekten 120 ay icin uretilir.

## Albaraka Konut live adapter V45
Albaraka calculator seceneklerinde `ProjectCode` / `CampaingCode` gibi ticari kodlar zamanla degisebildigi icin eski surumdeki sabit kampanya kodu eslesmesi kirilgan olabiliyordu.

V45:
- `ProductCode=KONTKRD` kimligini strict tutar,
- mevcut resmi selector'daki secenekleri canli kesfeder,
- "Ilk Evim" ve "2. ve Sonraki Konut" varyantlarini semantik label uzerinden cozer,
- guncel option JSON'unu oldugu gibi resmi calculator endpoint'ine gonderir,
- donen amount/maturity/rate/monthly/total ve payment plan butunlugunu yeniden dogrular.

Dolayisiyla yeni kampanya kodu yayinlandiginda production koduna yeni oran veya kampanya kodu hard-code etmek gerekmez.

## Albaraka 500.000 TL / 120 ay regresyonu
Kullanicinin resmi Albaraka hesaplama ekraninda gozlemledigi `%2,90` oran V45 testinde bir regression fixture olarak kullanilir. **Production kodunda %2,90 hard-code edilmez.** Testin amaci resmi live adapter'in donen guncel orani degistirmeden chatbot ve dashboarda aktardigini kanitlamaktir.

## Dashboard
Konut / Tasit / Ihtiyac senaryolarinda:
- Girilen tutar ve vade birebir korunur.
- Live mapping olan bankada canli sonuc yoksa `Resmi hesaplama araci su anda dogrulanamadi` yazilir.
- Eski rate ile satir doldurulmaz.
- `Resmi canli sonuc` metriği sadece exact VERIFIED live sonuc veren banka sayisidir.
- `Dogrulanmis BANSA modeli` yalniz live mapping bulunmayan ve verified deterministic source model ile hesaplanan bankalari sayar.

## Chatbot
Ayni resolver kullanilir. Exact amount/maturity sorusunda:
- live-mapped banka -> resmi live calculator,
- live basarisiz -> sayi yok / safe abstention,
- live mapping yok -> verified deterministic source model.

Cok-bankali karsilastirmada stale calculator snapshot ile current live quote ayni ranking havuzuna sokulmaz.

## Testler
Yeni V45 regresyonlari:
- live-mapped banka stale modele dusmez,
- Albaraka 500k / 120 live rate passthrough,
- vadesiz konut senaryosunda tek ortak 120 ay butunlugu,
- Albaraka dinamik campaign/project code discovery.

Calistirma:

```bash
python -m pytest -q tests/test_v45_live_authority_and_maturity_integrity.py tests/test_v44_official_live_calculators.py
```

Internetli smoke test:

```bash
python scripts/test_official_live_calculators_v45.py --family konut --amount 500000 --maturity 120
```

Bu smoke test production endpoint'lerini cagirir; `[VERIFIED]` satirlari dashboard/chatbotta kullanilabilecek exact live sonuclardir.
