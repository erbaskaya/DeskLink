# DeskLink v0.4.0 — tek tıkla başlayan Windows ve macOS uzak masaüstü

**Başlangıç:** [`BASLA-BURADAN.md`](BASLA-BURADAN.md).

Uygulamanın canlı Cloudflare relay adresi varsayılan olarak gelir. Son kullanıcı için amaç:
- Windows'ta tıklanabilen `DeskLink.exe`.
- macOS'ta tıklanabilen `DeskLink.app`, Intel ve Apple Silicon sürümleri.
- Son kullanıcı tarafında **Node.js ve Python kurulumu olmaması**.

Bu kaynak ZIP'in içerisinde önceden derlenmiş `DeskLink.exe`/`DeskLink.app` yok. GitHub Actions iş akışı üç işletim sistemi paketini bir seferde hazırlamak üzere eklendi. Alternatif olarak Windows/Mac'te yerel paketleme betikleri vardır. İstemci kodu Python ile yazılmıştır, ancak derlenmiş paket Python yorumlayıcısını içine alır.

Logo ve ikonlar `brand/` dizininde. `app_identity.py` sürüm, varsayılan sunucu ve ikon kaynak yolunu sağlar. Kod imzalama/noter onayı ve uçtan uca şifreleme henüz yapılmadı; test kullanımı içindir. `cloudflare/` içinde daha önce kurulmuş sunucunun kaynak kodu bulunur; onu yeniden dağıtmaya gerek yoktur.

Önceki ağ / izin belgeleri: `CLOUDFLARE-KURULUM-TR.md`, `MAC-KURULUM.md`.
