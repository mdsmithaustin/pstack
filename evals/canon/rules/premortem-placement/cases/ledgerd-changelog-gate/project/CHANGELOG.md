# Changelog

All notable changes to ledgerd. Format follows Keep a Changelog.

## Unreleased

### Fixed
- Postings with a zero amount no longer create an empty journal line.

## 2.14.0 (2026-09-02)

### Added
- `GET /accounts/{id}/balance?at=` returns the balance as of a timestamp.

### Changed
- Journal export uses RFC 3339 timestamps.

## 2.13.1 (2026-08-19)

### Fixed
- Reversal of a reversed posting returns 409 instead of creating a third posting.
