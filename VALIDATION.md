# Validation record

This record describes actual checks of the local AI Office implementation and their limits. It separates application development and validation from the demonstration workflow inside the product.

## Verified behavior

- Import of 282 original profiles in 18 categories; source Markdown SHA-256 and original instruction bodies match the supplied catalog.
- Primary-team bulk addition, unique membership, preserved existing configuration, safe repeat, fresh default boot and existing-database preservation.
- Searchable and paginated team, department pages, all-role executor search, and correction of the last page after removing its participants.
- Radial overview, relationship filters, hierarchy, department detail, zoom and camera reset.
- Ten-stage demo, nine concrete output handoffs, one visible field-label revision, retest, final owner approval, reset history and persistent materials.
- Custom task goal, priority, ordered named stages, materials and completion criteria persist across reload.
- Explicit autonomy/capabilities, cancellation, revoked export rights, scheduled start, locks and atomic result/event commit.
- Unique events, SSE replay, Last-Event-ID, reconnect snapshots and restart without silent provider retries.

## Recorded results

| Check | Result |
| --- | --- |
| Backend unit, integration and security contracts | 45 passed, including Russian-presentation regressions |
| TypeScript and Vite production build | Passed |
| Main browser workflow | 20 checks passed |
| Complete 282-member workflow | 15 checks passed |
| Russian-presentation workflow | 7 checks passed |
| axe accessibility | Eleven selected states, zero violations |
| Browser exceptions/unexpected network failures | Zero |
| Desktop 1440 px and mobile 390 / 320 px | No page-level horizontal overflow; long forms remain scrollable |
| npm audit | Zero known vulnerabilities in the recorded scan |
| pip-audit | 17 runtime dependencies, zero known vulnerabilities in the recorded scan |
| Docker Compose | `docker compose config --quiet` passed |

The Russian UI update includes localized role names/descriptions, Russian search, labels and task defaults while preserving source records and custom user settings. Current logs supersede earlier counts in screenshots or historical descriptions.

## Evidence

- `output/backend-tests.txt`: final backend test output.
- `output/playwright/browser-report.json`: main workflow, axe, console and network results.
- `output/playwright/localization-report.json`: Russian labels/descriptions/search, source language and narrow-screen regression.
- `output/playwright/all-agents-report.json`: complete-team, executor search, large departments and page-removal regression.
- `output/npm-audit.json`, `output/python-audit.json`: dependency audit snapshots.
- `tests/SECURITY_REVIEW.md`: source controls and executable security contracts.
- `docs/screenshots/`: selected rendered desktop/mobile evidence used by the README.
- `output/playwright/`: complete screenshot set.

## Scope and limits

The local application uses **DemoAdapter**. No paid provider call was performed. ModelAdapter is tested with HTTP MockTransport for payload isolation, reported usage, safe errors, result persistence and absence of demo fallback. Provider account access, real model output, billing and external integrations remain unverified.

The local Docker Engine was unavailable; the image/container was not locally built or run. Python plus the built React interface was tested separately. GitHub CI results are recorded by the repository's Actions page after publication.

axe checks do not establish full WCAG certification. Manual screen-reader testing and research with actual users were not conducted. Security source review and dependency audits are not a penetration test.

The application remains a single-owner local MVP without authentication or a public production deployment. See [SECURITY.md](SECURITY.md).

## Reproduction

See [docs/TESTING.md](docs/TESTING.md) for backend/browser/audit commands and isolated test storage. Use `python tools/package.py` to build and validate a portable source-and-UI ZIP.
