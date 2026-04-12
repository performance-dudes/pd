# pd — Performance Dudes Claude Code Plugin

Document signing and trust infrastructure for AI-first collaboration.

## Skills

| Skill | Description |
|---|---|
| `/pd:setup-signing` | One-time setup: generate key pair, create CSR, get certificate |
| `/pd:sign-document` | Sign a PDF with your X.509 certificate |
| `/pd:verify` | Verify a signed PDF against the Root CA |

## Scripts

All scripts use `uv run` — dependencies are auto-installed, no manual `pip install` needed.

```bash
# Setup (one-time)
uv run scripts/setup.py --username felixboehm --email felix@example.com --trust ../trust

# Sign a PDF
uv run scripts/sign.py document.pdf --trust ../trust

# Verify a signed PDF
uv run scripts/verify.py document.pdf --trust ../trust
```

## Install as Claude Code Plugin

```bash
claude plugin marketplace add performance-dudes/pd
claude plugin install pd@pd
```

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python package runner)
- [performance-dudes/trust](https://github.com/performance-dudes/trust) repo cloned locally
- `gh` CLI authenticated (for certificate issuance)
