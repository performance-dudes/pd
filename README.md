# pd — Performance Dudes Claude Code Plugin

Document signing and trust infrastructure for AI-first collaboration.

## Skills

| Skill | Description |
|---|---|
| `/pd:setup-signing` | One-time setup: install pyHanko, generate key pair, get certificate |
| `/pd:sign-document` | Sign a PDF with your X.509 certificate (PKCS#7 embedded signature) |
| `/pd:verify` | Verify a signed PDF against the Root CA |

## Install

```bash
claude plugin marketplace add performance-dudes/pd
claude plugin install pd@pd
```

## Requirements

- [performance-dudes/trust](https://github.com/performance-dudes/trust) repo cloned locally
- `gh` CLI authenticated
- Python 3 with pip

## How it works

1. **Setup** (`/pd:setup-signing`): generates a local key pair, creates a CSR, submits it to the trust repo for signing by your Issuing CA
2. **Sign** (`/pd:sign-document`): embeds a PKCS#7 digital signature in a PDF using your certificate + private key
3. **Verify** (`/pd:verify`): checks signatures in a PDF and traces them to the Root CA
