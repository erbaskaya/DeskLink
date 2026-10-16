# DeskLink v0.3.1 — Ücretsiz Cloudflare internet relay kurulumu

DeskLink, Windows ve macOS'un **farklı internet bağlantılarından** birbirine bağlanması için Cloudflare Workers **Free** ve SQLite tabanlı **Durable Objects** kullanabilir.

**Bu paket Cloudflare hesabınızda otomatik olarak kurulmuş değildir.** Cloudflare hesabına giriş ve deploy işlemini siz tamamlamalısınız. VPS, sabit IP, modem port yönlendirmesi ve satın alınmış alan adı gerekmez. `workers.dev` alt alan adı yeterlidir.

## 1. Gerekenler

Node.js, *yalnızca Cloudflare relay sunucusunu bir kez yüklemek / güncellemek için* gereklidir. Windows ve Mac DeskLink istemcileri Node.js kullanmaz. Node.js 20 desteği sona erdiği için 22 veya 24 kullanın; sisteminizde 24 zaten kuruluysa tekrar kurmayın.

- Ücretsiz [Cloudflare hesabı](https://dash.cloudflare.com/sign-up)
- **Node.js 22 veya üzeri** (öneri: Node.js 24 LTS; yalnızca Cloudflare dağıtımını yapan bilgisayarda): [resmî Node.js indirme](https://nodejs.org/en/download)
- Masaüstünde DeskLink v0.3.0 (Windows: `BASLAT-WINDOWS.bat`, Mac: `MAC-BASLAT.command`). İlk çalıştırmada Python 3.11+ ve gereken paketler gerekebilir.

## 2. Cloudflare relay'i yükleme

**Windows'ta kolay kurulum:** ZIP'i tümüyle ayıkla, `CLOUDFLARE-KUR-WINDOWS.bat` dosyasına çift tıkla. **v0.3.1 düzeltmesi:** Windows'ta `npm --version` komutu artık `call` ile çalıştırılır; komut penceresinin yanlışlıkla kapanması engellenir. İşlem sonunda pencere siz kapatana kadar açık kalır.

**Mac'te kolay kurulum:** ZIP'i ayıkla, `MAC-CLOUDFLARE-KUR.command` dosyasına çift tıkla. Açılmazsa Terminal'de `bash MAC-CLOUDFLARE-KUR.command` çalıştır.

**Elle kurulum (Windows PowerShell / Mac Terminal):** Önce `DeskLink-MVP/cloudflare` klasörüne geçin:

```sh
npm install
npx wrangler login
npx wrangler deploy
```

Wrangler oturum açmak için tarayıcı açar. Cloudflare hesabınıza **kendiniz** giriş yapın. Cloudflare Free hesabını kullanın; ücretli plana geçiş gerektiren bir seçenekle karşılaşırsanız kabul etmeden hata mesajını kontrol edin. Deploy başarıyla tamamlandığında buna benzer bir çıktı görürsünüz (örnek adres):

```text
https://desklink-relay.sizin-subdomaininiz.workers.dev
```

Cloudflare ücretsiz `workers.dev` adresini hesap adına göre oluşturur. `sizin-subdomaininiz` yer tutucudur; gerçek çıktıyı kullanın.

**Doğrulama:** Bu `https://` adresini tarayıcıda açın. `"status":"ok"` ve `"websocket":"wss://.../ws"` görmelisiniz. Bu sayfa uzaktan masaüstü uygulaması değildir; yalnızca relay sağlık kontrolüdür.

## 3. İki bilgisayarı farklı internetlerden bağlama

1. Windows'ta `BASLAT-WINDOWS.bat`, Mac'te `MAC-BASLAT.command` dosyasını açın.
2. DeskLink içindeki **Bağlantı Sunucusu** alanına **her iki cihazda da aynı** adresi girin: `wss://desklink-relay.SIZIN-ADRESINIZ.workers.dev/ws` ve **Uygula**'ya basın.
3. İki cihazda da 9 haneli **Bilgisayar ID** oluşmasını bekleyin. ID oluşmuyor ve “Bağlantı yok” yazıyorsa URL doğru mu / Cloudflare dağıtımı tamamlandı mı kontrol edin.
4. Kontrol edilen cihazın **9 haneli ID** ve **8 haneli geçici erişim kodunu** kontrol eden bilgisayara girin.
5. Kontrol edilen bilgisayardaki kullanıcı gelen isteği **onaylamadan** ekran aktarımı ve kontrol başlamaz.
6. Mac kontrol edilecekse macOS **Ekran Kaydı** ve **Erişilebilirlik** izinlerine onay verin (gerekiyorsa uygulamayı yeniden başlatın).

> Cloudflare ile farklı internetlerden bağlanırken `BASLAT-TEST-SUNUCU.bat`, `MAC-TEST-SUNUCU.command` veya `LAN-TEST-SUNUCU-WINDOWS.bat` **çalıştırmayın**; onlar yalnızca yerel denemeler için.

**Önemli:** Cloudflare URL'sini bir kez Uygula ile kaydedince DeskLink onu aynı cihazda sonraki açılışlarında kullanır. Her iki cihazı farklı `workers.dev` sunucularına bağlamayın.

## 4. Ücretsiz kota ve kullanım sınırları

Resmî Cloudflare dokümanları (Ekim 2026):

- Workers Free: **100.000 istek/gün**.
- SQLite tabanlı Durable Objects Free: **100.000 ücretlendirmeye esas istek/gün**, **13.000 GB-s/gün** çalıştırma süresi. Gelen WebSocket mesajları hesaplamada **20:1** oranıyla değerlendirilir; birebir sınırsız mesaj garantisi değildir.
- Kota aşılırsa ücretsiz planda işlemler hata vermeye başlar. Bu tasarım ücretsiz prototip ve ara sıra uzaktan destek içindir; sınırsız müşteri trafiği veya profesyonel AnyDesk performansı için değil.
- WebSocket Hibernation API, boşta bağlantı varken işlem süresi maliyetini düşürür; aktarılan JPEG görüntü akışı yine işlem/görüntü yükü oluşturur.

Kaynaklar: [Durable Objects fiyatlandırma](https://developers.cloudflare.com/durable-objects/platform/pricing/), [Workers limits](https://developers.cloudflare.com/workers/platform/limits/), [Durable Objects WebSocket](https://developers.cloudflare.com/durable-objects/best-practices/websockets/).

## 5. Güvenlik ve teknik sınırlamalar

- **WSS/TLS**, her cihaz ile Cloudflare arasındaki taşıma kanalını şifreler. **Uçtan uca şifreleme YOKTUR:** Cloudflare relay servisi ekran görüntülerini ve kontrol komutlarını işleyebilir. Bu ilk sürüm hassas veri, müşteri desteği veya denetimsiz uzaktan erişim için güvenlik değerlendirmesi yapılmadan kullanılmamalıdır.
- Relay 8 haneli kodu denetler; hatalı kodları IP bazında sınırlar ve **karşıdaki kullanıcıdan görünür onay ister**. Herhangi bir gizli servis kurulmaz.
- Merkezi Durable Object, aynı anda çok sayıda yüksek FPS oturumu için tasarlanmadı. Yaklaşık 5 FPS JPEG aktarımı ile prototip niteliğindedir.
- Aynı bilgisayara kendi bilgisayarından bağlanıldığında **sonsuz ayna döngüsü oluşabilir**. Kullanıcının isteği üzerine 0.1.6'daki pencere gizleme/karartma koruması geri alınmış olarak kalmıştır.
- Hazır `DeskLink.exe` veya `.app` ikilileri pakette bulunmaz: Windows/Mac kaynak sürümü ve o sistemlerde paketleme betikleri bulunur. Mac ekranı/izinleri gerçek Mac üzerinde ayrıca doğrulanmalıdır.
- Cloudflare hesabının kullanıcı adı, şifresi veya API token'ı hiçbir DeskLink dosyasına yazılmamalı, kimseyle paylaşılmamalıdır.

## 6. Dosyalar

- `cloudflare/src/index.js`: Cloudflare Worker WebSocket girişi ve sağlık kontrolü
- `cloudflare/src/hub.js`: Hibernation destekli Durable Object relay protokolü, onay, 30 sn istek süresi, hız sınırlama
- `cloudflare/wrangler.jsonc`: Workers/SQLite Durable Object yapılandırması (Free plan uyumlu)
- `cloudflare/package.json`: Wrangler geliştirme aracı
- `cloudflare/tests/relay.test.mjs`: Node.js ile protokol simülasyon testleri
- `CLOUDFLARE-KUR-WINDOWS.bat` / `MAC-CLOUDFLARE-KUR.command`: interaktif sunucu dağıtımı

## 7. Hata alırsanız

- `No such module` / `wrangler bulunamadı`: `cloudflare` klasöründe `npm install` çalıştırın.
- `Node 22+`: Node.js'i güncelleyin ve yeni CMD / Terminal açın.
- `Not logged in`: `npx wrangler login` çalıştırıp açılan tarayıcıda giriş yapın.
- `durable_objects` veya `new_sqlite_classes` hatası: `wrangler.jsonc`'yi değiştirmeden dağıtımın hata metnini paylaşın. Proje yeni SQLite DO sınıfı kullanır; eski KV DO kullanmaz.
- `Deployment succeeded` ama DeskLink ID göstermiyor: `https://...workers.dev` URL'sinde `status: ok` olduğundan emin olun. DeskLink'te `https://` yerine `wss://` ve sonuna `/ws` kullanın.
- `Timeout` veya `429` / kota uyarısı: Cloudflare ücretsiz planda sınır dolmuş olabilir; Workers & Pages analitiklerini inceleyin.

**Not:** Node.js tabanlı protokol testleri bu paket oluşturulurken yerel olarak yürütüldü; ancak gerçek Cloudflare hesabına dağıtım, iki farklı internetten bağlantı ve gerçek Windows–Mac donanım testi tamamlanmadı.
