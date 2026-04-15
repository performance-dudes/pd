# pd

Claude Code plugin for PDF document signing and verification against the Performance Dudes trust infrastructure.

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

## Adding a skill

1. Create `skills/<name>/SKILL.md` with `name` and `description` frontmatter
2. Skills must be exactly one level deep: `skills/<name>/SKILL.md` (not nested in subdirectories)
3. Reference docs go in `skills/<name>/references/`
4. Bump `version` in `.claude-plugin/plugin.json` so the cache refreshes
5. Commit, push, `claude plugin install pd`, `/reload-plugins`
