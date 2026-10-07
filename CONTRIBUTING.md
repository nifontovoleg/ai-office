# Contributing

This private repository is maintained by its owner. Changes should keep the local application runnable and preserve existing project data.

1. Work on a focused branch.
2. Use English code identifiers, comments, documentation and commit messages; use Russian interface text.
3. Keep original catalog records and SHA-256 provenance intact. Put translations in the presentation layer.
4. Preserve custom names, autonomy settings, tool grants, material history and project isolation.
5. Rebuild `frontend/dist` after changing UI source.
6. Run checks appropriate to the change; use isolated storage for browser tests.
7. Review staged files for secrets and dependency/state directories before pushing.

The API and engine enforce permissions. Do not add execution privileges by interpreting text from a role profile or model output. Document any new provider/tool boundary and cover it with meaningful contract tests.

Use concise conventional commit subjects such as `fix(team): clamp removed member page` or `docs: explain model configuration`. Pull requests should explain the concrete behavior change, relevant validation, and any remaining limits.

See [development](docs/DEVELOPMENT.md), [testing](docs/TESTING.md), and [security](SECURITY.md).
