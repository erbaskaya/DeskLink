# DeskLink v0.5.0 — Kayıtlı bilgisayarlar ve tek ID ile onaylı erişim

**Yeni:** Karşı cihazın 9 haneli ID'sini bir kez yazın. Bağlantı kabul edildiğinde cihaz kaydedilir. Daha sonra **Kayıtlı Bilgisayarlar** listesinden seçip **BAĞLAN** butonuna basın; karşı tarafta onay isteği açılır. **8 haneli ikinci kod yoktur.**

- Bilgisayar ID'si artık ayarlar dosyasında kalıcıdır ve her açılışta değişmez.
- Yeni sürüm ilk kez açıldığında eski geçici ID yerine yeni bir kalıcı ID oluşturulur.
- Cihaz sahipliği rastgele oluşturulan 256 bit gizli anahtarla relay tarafından doğrulanır.
- Gelen isteklerde onay zorunludur, onaysız erişim veya görünmez arka plan servisi yoktur.
- Kayıtlı cihazların ismi değiştirilebilir ve silinebilir. Kayıtlar sadece o kullanıcı bilgisayarında saklanır.
- Cloudflare Worker güncellenmeli ve **iki tarafta da DeskLink 0.5.0** kullanılmalıdır.

## Kurulum (önce Cloudflare güncellemesi)

1. Sunucuyu kurduğunuz Windows PC'de **`CLOUDFLARE-GUNCELLE-WINDOWS.bat`** dosyasını çalıştırın. Mevcut `desklink-relay.erbaskayam.workers.dev` adresi değişmez. Node.js burada gerekir; uzak PC veya Mac'te gerekmez.
2. Güncel kaynakları GitHub `erbaskaya/DeskLink` reposuna yükleyin.
3. GitHub **Actions → DeskLink portable Windows + macOS → Run workflow** ile EXE ve Mac DMG dosyalarını oluşturun.
4. Her iki bilgisayarda **yeni** DeskLink'i açın. Cloudflare adresi otomatik gelir.

Windows uygulaması `.exe`, Mac uygulaması `.app`/`.dmg` şeklinde dağıtılır. Karşı kullanıcıda **Python ve Node.js gerekmez.** Derlenmiş dosyalar bu kaynak paketinin içinde yoktur; GitHub Actions oluşturur.

## Kayıt ve bildirim

- Bir cihazın ID'sini girip Bağlan deyin. Karşı bilgisayarda DeskLink **açık ve Cloudflare'a bağlı** olmalıdır.
- Karşı tarafa bildirim gider ve gelen cihazın doğrulanmış ID'si gösterilir.
- **İzin Ver** ile ekran ve fare/klavye kontrolü açılır; **Reddet** ile kapalı kalır.
- İlk başarılı bağlantıdan sonra cihaz sizin listene otomatik kaydedilir.
- Dilerseniz bağlanmadan önce ID girip **ID'yi kaydet** butonunu kullanabilirsiniz.

**Güvenlik sınırı:** Bu sürümde uçtan uca şifreleme yoktur; Cloudflare relay ekrana ve kontrol trafiğine erişebilir. Hassas veri içeren cihazlarda kullanmayın; sonraki sürümde E2E, audit ve kod imzalama şarttır. Kaydetmek kimseye kalıcı kontrol izni vermez. Ayrıca uygulama kapalıyken istek gösterilmez. Sunucuda istek sıklığı sınırlandırılır.

## Depolama

Windows `%APPDATA%\DeskLink\settings.json`, Mac `~/Library/Application Support/DeskLink/settings.json`. Bu dosya cihaz kimliği için gizli anahtar içerir; başkalarıyla paylaşmayın. Aynı dosyanın yedeği alınıp geri yüklenirse ID ve kayıtlı cihazlar korunabilir. Silinirse yeni ID atanır.

## Testler

`python -m unittest discover -s tests -v` ve `node --test cloudflare/tests/*.test.mjs`. Geliştirici makinesinde Python/Node gerekebilir, bitmiş EXE/APP kullanıcılarında gerekmez. Gerçek iki Windows/Mac donanımında bu sürüm henüz test edilmemiştir.
