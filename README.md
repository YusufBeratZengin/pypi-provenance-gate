# PyPI Provenance Gate

Check PEP 740 provenance for every package in your lockfile and catch regressions.

`provenance-gate` reads a lockfile (`uv.lock`, `poetry.lock`, `pylock.toml` or a
hash-pinned `requirements.txt`), asks the PyPI Integrity API for the provenance of
every release file, and reports whether the package is `attested`, `unattested`,
`partial`, `unknown` or `skipped` (non-PyPI index).

## Install

```console
pip install pypi-provenance-gate
```

## Usage

```console
provenance-gate uv.lock
provenance-gate requirements.txt --json
provenance-gate uv.lock --onceki HEAD~1 --ci
provenance-gate poetry.lock --politika politika.toml
```

Exit codes: `0` no policy error, `1` policy error, `2` usage/lockfile/git error.

Common options:

- `--surum`, `--version` – print the version and exit (`0`), no lockfile needed.
- `--ci` – strict policy where every finding is an error.
- `--izin NAME` – allow an unattested package by name or `name==version`.
  Names are normalised with PEP 503 rules, exactly like policy-file entries, so
  `Foo_Bar`, `foo.bar` and `foo-bar` are equivalent.
- `--beklenen PATH` – check expected publishers from `beklenen.toml`; on its own
  this enables only the expected-publisher check and does not make other findings
  errors.
- `--politika PATH` – read `politika.toml` (severity per rule, allowlist, expected
  publishers).
- `--onceki REV` – compare with the lockfile at a git revision and flag
  provenance regressions and publisher changes.
- `--onbellek-yok`, `--cevrimdisi` (`--offline`), `--istek-limiti`,
  `--dosya-limiti` – cache and request controls.

## Policy files

```toml
[genel]
kanitsiz = "uyari"          # hata | uyari | yoksay
kismi = "uyari"
bilinmiyor = "uyari"
kanitsiz_izin = ["some-package", "other-package==1.2.3"]

[beklenen]
some-package = "github.com/example-org/some-package"
```

`beklenen.toml` accepts the same table under `[depolar]` or `[beklenen]`.

The expected-publisher check runs for attested and partial packages: if any
attested release file comes from a repository other than the expected one, a
`yayinci_uyumsuz` finding is produced.

## Scope

Provenance shows which identity published a file. It does not prove that the
package is safe or free of malware.
