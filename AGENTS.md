# pd

Claude Code plugin for PDF document signing and verification against the Performance Dudes trust infrastructure.

> **⚠️ Deprecated as a plugin marketplace.** `pd@pd` no longer takes **new
> skills** — new skills/plugins belong in the `ai-plugins` marketplaces
> (`ai-plugins`, `ai-plugins-internal`, `ai-plugins-enterprise`). Only the
> **active signing infrastructure** stays here (`scripts/`, skills
> `setup-signing` / `sign-document`). Do not add anything new here.

## Installation

Requires the [base workspace repo](https://github.com/performance-dudes/performance-dudes) as parent directory.

```bash
cd performance-dudes          # base workspace
git clone git@github.com:performance-dudes/pd.git
claude plugin marketplace add ./pd
claude plugin install pd
```

The base repo's `.claude/settings.json` also declares this marketplace, so new clones get it automatically.

## Skills

| Skill | Description |
|-------|-------------|
| `pd:setup-signing` | Generate key pair, create CSR, write signer config |
| `pd:sign-document` | Sign a PDF with PKCS#7 + optional visible stamp + RFC 3161 timestamp |

> **Migrated to the `ai-plugins` marketplaces (the deprecated `pd@pd` part):**
> `git-worktrees` and `project-structure` now live in
> `workspace@ai-plugins-internal`, `bank-vertragsgestaltung` in
> `sales@ai-plugins-internal`. `pd` keeps only the signing skills, which belong
> to the active signing infrastructure (`scripts/*.py`).

## Adding a skill

1. Create `skills/<name>/SKILL.md` with `name` and `description` frontmatter
2. Skills must be exactly one level deep: `skills/<name>/SKILL.md` (not nested in subdirectories)
3. Reference docs go in `skills/<name>/references/`
4. Bump `version` in `.claude-plugin/plugin.json` so the cache refreshes
5. Commit, push, `claude plugin install pd`, `/reload-plugins`
