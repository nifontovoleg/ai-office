# Agency Agents catalog

This directory contains the original role material imported by AI Office:

- `agents.json`: schema-versioned catalog with 282 profiles in 18 categories.
- `profiles/`: all 282 original Markdown role files.
- `starter-team.json`: eight concrete profile IDs used by newly created projects and the demonstration workflow.

## Provenance

The source is the user-supplied `agency-agents-0.3.2-1.x86_64.cpio` package. Its version, archive SHA-256 and original archive paths are recorded in `agents.json`. Only regular Markdown files from the catalog baseline were extracted; executables and symbolic links were not imported or run.

Each profile retains its original ID, name, description, instruction body, source path and file SHA-256. The full source Markdown contains YAML frontmatter; `instructions_md` contains the instruction body. Source identity and integrity are tested separately from project membership and presentation.

## Russian presentation

The API supplies separate `display_name_ru` and `description_ru` values for the interface. The localization layer does not modify original names, descriptions, instructions or source checksums. Custom member display names remain project settings.

The primary office is seeded with all roles only on a fresh database. Other new projects start with the eight-member team. Bulk addition extends any project safely without duplicate members or changed existing configurations.

## Source rights

No new license for the supplied profiles is granted here. See [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) before redistribution.
