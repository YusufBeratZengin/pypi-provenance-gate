# PyPI Provenance Gate

Kilit dosyanızdaki her paket için PEP 740 provenance (kanıt) durumunu denetler ve
gerilemeleri yakalar.

`provenance-gate`, bir kilit dosyasını (`uv.lock`, `poetry.lock`, `pylock.toml`
veya hash ile sabitlenmiş `requirements.txt`) okur, her yayın dosyası için PyPI
Integrity API'ye sorar ve paketi `attested`, `unattested`, `partial`, `unknown`
veya `skipped` (PyPI dışı indeks) olarak bildirir.

## Kurulum

```console
pip install pypi-provenance-gate
```

## Kullanım

```console
provenance-gate uv.lock
provenance-gate requirements.txt --json
provenance-gate uv.lock --onceki HEAD~1 --ci
provenance-gate poetry.lock --politika politika.toml
```

Çıkış kodları: `0` politika hatası yok, `1` politika hatası, `2` kullanım/kilit
dosyası/git hatası.

Sık kullanılan seçenekler:

- `--surum`, `--version` – sürümü yazıp çıkar (`0`); kilit dosyası gerekmez.
- `--ci` – her bulgunun hata olduğu katı politika.
- `--izin AD` – kanıtsız pakete ada veya `ad==sürüm` biçimine göre izin verir.
  Adlar politika dosyasındaki girdilerle aynı PEP 503 kurallarıyla normalleştirilir;
  `Foo_Bar`, `foo.bar` ve `foo-bar` eşdeğerdir.
- `--beklenen YOL` – `beklenen.toml` içindeki beklenen yayıncıları denetler. Tek
  başına kullanıldığında yalnız beklenen yayıncı kuralını etkinleştirir; diğer
  bulguları hataya çevirmez.
- `--politika YOL` – `politika.toml` okur (kural başına seviye, izin listesi,
  beklenen yayıncılar).
- `--onceki REV` – kilit dosyasını bir git revizyonuyla karşılaştırır; kanıt
  gerilemesini ve yayıncı değişimini bildirir.
- `--onbellek-yok`, `--cevrimdisi` (`--offline`), `--istek-limiti`,
  `--dosya-limiti` – önbellek ve istek denetimleri.

## Politika dosyaları

```toml
[genel]
kanitsiz = "uyari"          # hata | uyari | yoksay
kismi = "uyari"
bilinmiyor = "uyari"
kanitsiz_izin = ["bir-paket", "diger-paket==1.2.3"]

[beklenen]
bir-paket = "github.com/example-org/bir-paket"
```

`beklenen.toml` aynı tabloyu `[depolar]` veya `[beklenen]` altında kabul eder.

Beklenen yayıncı denetimi kanıtlı ve kısmi paketlerde çalışır: kanıtlı herhangi bir
yayın dosyası beklenenden farklı bir depodan geldiyse `yayinci_uyumsuz` bulgusu
üretilir.

## Kapsam

Provenance, bir dosyayı hangi kimliğin yayımladığını gösterir. Paketin güvenli
veya kötü amaçlı yazılımdan arınmış olduğunu kanıtlamaz.
