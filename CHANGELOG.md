# Changelog

All notable changes to ProofKit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2025-08-09 - Production Launch 🚀

### Added
- Complete billing system with Stripe integration (Free/Starter/Pro/Enterprise tiers)
- Live examples page with real-time verification timestamps
- Comprehensive monitoring and alerting (p95 compile, 5xx rate, bundle errors)
- GA4 and Google Ads conversion tracking with UTM capture
- Trust page showing validation campaign status (12/12 green)
- Better Uptime status integration in footer
- Premium certificate SKU ($12 one-off with enhanced features)
- DMARC implementation plan for email deliverability
- Idempotent metrics emission for Prometheus/Grafana
- Evidence bundle verification with SHA-256 integrity checks

### Changed
- API v2 now default (v1 still supported via backward-compatible shim)
- CI/CD consolidated to single pipeline (<90s target runtime)
- Safe Mode completely removed - production ready
- Examples now generated live via API with fresh timestamps
- All 6 industries fully operational (powder, autoclave, sterile, HACCP, concrete, coldchain)

### Fixed
- Bundle root hash verification now deterministic
- PDF generation without QA watermarks
- All industry pages loading correctly
- Parser handling for vendor CSV formats
- TSA timestamp resilience (non-blocking with retry queue)

### Security
- Cookie consent gating for all analytics
- RFC 3161 timestamp support for legal non-repudiation
- PDF/A-3 compliance for long-term archival

## [0.5.0] - 2025-08-08

### Added
- Initial staging deployment
- Shadow verification system
- Required signals enforcement
- Parser warnings infrastructure

### Changed
- Industry-specific validation algorithms
- Acceptance test framework

## [0.4.0] - 2025-08-07

### Added
- Magic link authentication
- Email system with Postmark
- AWS S3 evidence storage

## [0.3.0] - 2025-08-06

### Added
- PDF/A-3 generation
- QR code verification
- Evidence bundle creation

## [0.2.0] - 2025-08-05

### Added
- Multi-industry support
- API v2 specification
- Web interface

## [0.1.0] - 2025-08-04

### Added
- Initial release
- Powder coating validation
- Basic CSV processing
- PDF certificate generation