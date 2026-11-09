# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-09

### Added

- Check PEP 740 provenance for every release file in `uv.lock`, `poetry.lock`,
  `pylock.toml` and hash-pinned `requirements.txt`.
- Compare against a previous git revision with `--onceki` to catch regressions.
- Policy file, expected publishers (`--ci` strict mode) and CI exit codes.
- English and Turkish documentation (`README.md`, `README.tr.md`).

[Unreleased]: https://github.com/YusufBeratZengin/pypi-provenance-gate/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/YusufBeratZengin/pypi-provenance-gate/releases/tag/v0.1.0
