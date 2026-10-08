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
| Backend unit, integration and security contracts | 84 passed, including Codex, OpenCode/provider and Russian-presentation regressions |
| Real Codex text-stage smoke | Passed with saved ChatGPT login and CLI default; Russian text and token counters captured |
| Real OpenCode Big Pickle smoke | Passed with public free authentication; text returned, no tool events, CLI-reported cost `0` |
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

The October 8 Codex/OpenCode update brings the backend suite to 84 tests. Offline tests cover both API protocols and CLI dispatch, saved-login requirements, startup notices, restricted tool handling, usage, cancellation and stage handoffs. OpenCode tests cover free/ChatGPT/API modes, fixed Big Pickle main/small models, whitelist/public authentication and credential boundaries. All tests passed without live provider requests. Separate real Codex and OpenCode Big Pickle text smokes also passed; they are not part of the offline suite. The existing browser/accessibility rows describe the earlier full UI validation; those browser suites were not rerun for this connection update. The Russian connection hint was updated and the production bundle was rebuilt.

## Evidence

- `output/backend-tests.txt`: final backend test output.
- `output/codex-smoke.json`: sanitized real Codex response, saved-login transport, CLI-default model selection and reported token usage; no credentials or authentication files.
- `output/big-pickle-smoke.json`: real OpenCode CLI text response from `opencode/big-pickle`, public free route, reported tokens/cost and zero tool events.
- `output/playwright/browser-report.json`: main workflow, axe, console and network results.
- `output/playwright/localization-report.json`: Russian labels/descriptions/search, source language and narrow-screen regression.
- `output/playwright/all-agents-report.json`: complete-team, executor search, large departments and page-removal regression.
- `output/npm-audit.json`, `output/python-audit.json`: dependency audit snapshots.
- `tests/SECURITY_REVIEW.md`: source controls and executable security contracts.
- `docs/screenshots/`: selected rendered desktop/mobile evidence used by the README.
- `output/playwright/`: complete screenshot set.

## Scope and limits

Fresh source launches use **DemoAdapter** until the owner explicitly enables and selects a real executor. The primary template now uses `codex_cli`. The live smoke on October 8 invoked `ModelAdapter` with saved Codex ChatGPT login and the CLI default, returned a Russian three-item QA checklist, and reported 15,606 input / 74 output tokens. It used account allowance; no API key was supplied. The recorded cost remains unknown. This proves text transport, not customer-project coding, automatic tool execution or unlimited account access.

The separate Big Pickle smoke ran the installed OpenCode CLI 1.18.18 in an empty temporary folder, using public free authentication, the built-in coding agent and tool confirmation. It returned a short Russian confirmation without tool events and reported cost `0`. An initial all-tools-denied smoke received Zen `403`; using the normal confirmation policy resolved it. This demonstrates a current response, not future uptime, unchanged free pricing or customer-project development. Big Pickle's documented free period is limited and collected data may be used to improve the model.

ModelAdapter's Chat Completions and native Claude Messages protocols are tested with HTTP MockTransport for payload isolation, reported usage, safe errors, result persistence and absence of demo fallback. Empty-key presets and CLI helpers were checked locally; interactive launch behavior was tested with mocked subprocesses. Direct API provider accounts/billing, optional OpenCode OAuth/API login, actual customer-project tool execution and interactive customer coding remain unverified. OpenCode is a separate CLI session and is not registered as an office stage executor.

The local Docker Engine was unavailable; the image/container was not locally built or run. Python plus the built React interface was tested separately. GitHub CI results are recorded by the repository's Actions page after publication.

axe checks do not establish full WCAG certification. Manual screen-reader testing and research with actual users were not conducted. Security source review and dependency audits are not a penetration test.

The application remains a single-owner local MVP without authentication or a public production deployment. See [SECURITY.md](SECURITY.md).

## Reproduction

See [docs/TESTING.md](docs/TESTING.md) for backend/browser/audit commands and isolated test storage. Use `python tools/package.py` to build and validate a portable source-and-UI ZIP.
