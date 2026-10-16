# DeskLink Mac — Hızlı kurulum

**Mac'te çalıştırılacak dosya:** `MAC-BASLAT.command`

1. Mac'e resmi Python 3.11+ (Tkinter dahil) yükleyin: https://www.python.org/downloads/macos/
2. ZIP'i ayıklayın, `MAC-BASLAT.command` dosyasını çift tıklayın. İlk açılışta paketler indirilir; internet gerekir. Açılmazsa Terminal'de proje klasöründe `bash MAC-BASLAT.command` çalıştırın.
3. Mac başkası tarafından kontrol edilecekse DeskLink ekranındaki iki izin düğmesine basın. macOS **Sistem Ayarları → Gizlilik ve Güvenlik** altında *Ekran ve Sistem Sesi Kaydı* ile *Erişilebilirlik* izinlerini verin. Ardından uygulamayı tamamen kapatıp yeniden açın. Terminal'den çalıştırıldığında izin istemi Terminal veya Python adına gelebilir.
4. Windows ve Mac **farklı bilgisayarlarsa** `127.0.0.1` kullanmayın. İkisi de aynı `wss://relay...` sunucusuna bağlanmalıdır. Sadece güvendiğiniz LAN'da test edecekseniz Mac'te `MAC-LAN-TEST-SUNUCU.command`, Windows'ta `LAN-TEST-SUNUCU-WINDOWS.bat` seçeneğinden **yalnızca birini** çalıştırın. İki istemcide `ws://SUNUCU_IP:8765` yazın (örnek `ws://192.168.1.50:8765`). Yerel sunucuyu internete açmayın.
5. Mac'te çift tıklanabilir `.app` üretmek istiyorsanız (Mac'in **kendisinde**) `MAC-APP-OLUSTUR.command` dosyasını çalıştırın. Çıktı `dist/DeskLink.app` olacaktır. Dağıtım için Apple imzalama/noter onayı gereklidir.

**Not:** Sonsuz ekran koruması isteğiniz üzerine **kaldırıldı**. Aynı bilgisayara kendi üzerinden bağlanırsanız ayna görüntüsü oluşabilir. Bu ZIP'de derlenmiş `.app` yoktur; Mac testleri henüz gerçek donanımda yapılmamıştır.

Ayrıntılar: `README-TR.md`.
