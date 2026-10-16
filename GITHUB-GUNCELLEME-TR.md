# DeskLink v0.5.0 - GitHub ve Cloudflare guncellemesi

Bu surumde bilgisayar ID'si kalicidir. Karsi bilgisayara yalnizca ID ile baglanti istegi gonderilir. Karsi tarafta izin penceresi acar. Onceki baglantilar otomatik kaydedilir.

## Once Cloudflare'i guncelleyin

DeskLink sunucusunu kurdugunuz Windows bilgisayarda kaynak klasorundeki `CLOUDFLARE-GUNCELLE-WINDOWS.bat` dosyasina cift tiklayin. Dosya `cloudflare/src/hub.js` ve diger sunucu kodlarini **ayni** `desklink-relay` Worker'ina yukler. Yeni bir Cloudflare hesabi/Workers adresi istemez.

Deploy sonucu ornek adres: `https://desklink-relay.erbaskayam.workers.dev`. Normal kullanim `wss://desklink-relay.erbaskayam.workers.dev/ws`.

**Onemli:** Yeni istemciler mevcut eski Cloudflare koduyla calismaz. Worker once guncellenmelidir.

## GitHub'a dosyalari guncelleyin

Repo: https://github.com/erbaskaya/DeskLink

### Tavsiye edilen: GitHub Desktop

1. GitHub Desktop ile `erbaskaya/DeskLink` reposunu bilgisayariniza klonlayin (bir kere yeterlidir).
2. `DeskLink-v0.5.0-GitHub-Degisen-Dosyalar.zip` dosyasini ayiklayin ve `DeskLink` reposunun **ana klasorune**, ayni dosyalari degistirerek kopyalayin. Alt klasorleri (`cloudflare/src`, `tests`) koruyun.
3. GitHub Desktop'ta degisiklikleri goreceksiniz. `Summary: DeskLink 0.5.0 kalici ID ve kayitli PC` yazin, `Commit to main` ve `Push origin` tiklayin.
4. GitHub → Actions → **DeskLink portable Windows + macOS** → **Run workflow** → Run workflow.
5. Islem basariliysa `Artifacts` alanindan Windows `.exe`, Mac Intel `.dmg`, Mac Apple Silicon `.dmg` indirin.

### Tarayicidan

Mevcut dosyalarin icerigini GitHub'daki kalem (Edit) simgesiyle degistirip **Commit changes** yapabilirsiniz; yeni `device_store.py`, yeni `tests/test_device_store.py` ve `CLOUDFLARE-GUNCELLE-WINDOWS.bat` dosyalarini da **Add file** ile ekleyin. Birden fazla dosyayi tek seferde aktarmak icin dosya yukleme ekranina ayikladiginiz klasorleri suruklemeyi deneyebilirsiniz. GitHub yeni dosya yapisini korumali ve mevcut dosyalari guncellemelidir. Dosyalarin GitHub'da depo kokunde olmalarini kontrol edin.

## Dikkat

* **Iki tarafta da** DeskLink 0.5.0 olmalidir. Eski v0.4.0'daki gecici ID'ler korunmaz; yeni surum ilk acilista tek seferlik kalici ID uretir.
* MAC/Windows programini kullanacak kisiler Python ya da Node.js kurmaz; GitHub derlemeleri bu calisma ortamlarini icinde tasir.
* Karsi bilgisayarda program acik ve bagli olmalidir; her baglanti icin **acik yerel onay gerekir**.
* Cloudflare relay mesaji ve ekran goruntusunu gorebilir; **uctan uca sifreleme henuz yok**. Guvenilir test cihazlari disinda kullanmayin.
* Cihazin gizli anahtari `%APPDATA%\DeskLink\settings.json` veya Mac `~/Library/Application Support/DeskLink/settings.json` icinde saklanir. Bu dosyayi paylasmayin.
