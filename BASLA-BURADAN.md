# DeskLink v0.5.0 — Tek tıkla açılan Windows / Mac uygulaması

> **Bu ZIP, kaynak kod + ikonlar + otomatik derleme altyapısıdır. ZIP'in içinde henüz Windows .exe veya macOS .app bulunmaz.** Onlar ayrı işletim sistemlerinde paketlenmelidir. GitHub Actions bu işi otomatik yapar.

## Nihai kullanıcı için — Python ve Node.js gerekli değil

- **Windows 64 bit**: `DeskLink.exe` dosyasını çift tıkla. Kurulum sihirbazı veya Python / Node.js gerekmez.
- **Mac M1/M2/M3/M4/M5... (Apple Silicon)**: `DeskLink-macOS-arm64.dmg` dosyasını aç, `DeskLink.app` dosyasını Uygulamalar'a taşı, sonra DeskLink'i aç.
- **Intel Mac**: `DeskLink-macOS-x86_64.dmg` ile aynı işlem.
- Varsayılan Cloudflare adresi: `wss://desklink-relay.erbaskayam.workers.dev/ws`. İstemci otomatik bağlanır, URL girmek gerekmez. Kurulmuş eski DeskLink ayarı varsa onu değiştirmek gerekebilir.
- Uzaktan kontrol her oturumda **karşı tarafın iznini** gerektirir. Mac'in ekranını paylaşmak için macOS Ekran Kaydı + Erişilebilirlik izinleri de gerekir.
- **Not:** Şimdilik deneysel sürümdür. Uçtan uca şifreleme ve gerçek Windows/Mac paketlerinin saha testleri tamamlanmadı. Gizli müşteri verileriyle kullanmayın.

## Bu kaynak ZIP'ten gerçek .exe ve .app nasıl üretilir?

**Tercih edilen yol: GitHub Actions (tek kere kurulur, iki platformu da internet üzerinden derler)**

1. GitHub'da yeni bir repo oluşturun (ör. `DeskLink`). Repo **özel** olabilir; GitHub Actions ücretsiz kullanım kotası ve Mac çalıştırma maliyetleri planınıza bağlıdır.
2. Bu ZIP'teki `DeskLink/` klasörünün **içeriğini** deponun köküne yükleyin. `.github/workflows/desktop-binaries.yml` yolunu mutlaka koruyun.
3. GitHub'da **Actions → DeskLink portable Windows + macOS → Run workflow** adımını çalıştırın.
4. İşler tamamlandığında, aynı Actions çalışmasının **Artifacts** bölümünden şu üç dosyayı alın:
   - `DeskLink-Windows-x64` → içinde `DeskLink.exe` bulunur.
   - `DeskLink-macOS-x86_64` → Intel Mac için DMG.
   - `DeskLink-macOS-arm64` → Apple Silicon Mac için DMG.
5. Çıkan EXE veya DMG'yi hedef PC/Mac'lere gönderin. **Karşı bilgisayarların hiçbiri Node.js/Python kurmaz.**

**Alternatif — kendi bilgisayarında derleme:**

- Windows geliştirme PC'sinde `WINDOWS-EXE-OLUSTUR.bat` ile `dist/DeskLink.exe` oluşur. Python yalnızca bu **derleyen bilgisayarda** gereklidir.
- Mac geliştirme bilgisayarında `MAC-APP-OLUSTUR.command` ile `dist/DeskLink.app` oluşur. Python yalnızca derleyen Mac'te gereklidir.
- macOS uygulaması Windows'ta ve Windows EXE'si Mac'te derlenmez. PyInstaller'ın kısıtlamasıdır.

## Önemli notlar

- Windows uygulaması kod imzasızdır; SmartScreen uyarısı görülebilir. Mac DMG'ler Apple geliştirici imzası/noter onayı **olmayan** test paketleridir ve Gatekeeper açmayı engelleyebilir. Yaygın dağıtım için imzalama ve notarization gerekir.
- Hedef bilgisayarda Python/Node kurulumu gerekmez ama macOS güvenlik izinleri gene gerekir.
- Bağlantı 5 FPS JPEG aktarım prototipidir. Dosya aktarımı, ses, uçtan uca şifreleme ve otomatik güncelleme henüz yoktur.
- Cloudflare Workers Free hesabında kota limitleri geçerlidir; merkezi sunucu yönetimi için Node.js yalnızca **sunucuyu dağıtan** bilgisayarda kullanılır.
- Kaynak koddaki `brand/` klasörü PNG, SVG, Windows ICO, macOS ICNS ve açık/koyu renkli logo dosyalarını içerir.
