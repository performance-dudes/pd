# pd — Performance Dudes Claude Code Plugin

Document signing and trust infrastructure for AI-first collaboration.

Sign PDFs locally with a cryptographic PKCS#7 signature plus a visible handwritten signature stamp. Certificates are managed via the [performance-dudes/trust](https://github.com/performance-dudes/trust) PKI. On macOS, Touch ID unlocks the signing key.

## Scripts

All scripts run via `uv run` — dependencies are installed automatically on first run.

| Script | Purpose |
|---|---|
| `scripts/setup.py` | Generate key pair + CSR, write config |
| `scripts/extract-signature.py` | Extract signature PNG from a Preview-signed PDF |
| `scripts/harden-signing.sh` | Encrypt the private key + store passphrase in macOS Keychain (Touch ID) |
| `scripts/sign.py` | Sign a PDF with PKCS#7 + visible stamp |
| `scripts/verify.py` | Verify signatures against the Root CA |

---

## Quick start — test the full flow

Assumes you have cloned both `pd` and `trust` as siblings:

```
work/
├── pd/         ← you are here
└── trust/      ← the public PKI repo
```

### Prerequisites

- macOS (for Touch ID integration; signing works on Linux too)
- [uv](https://docs.astral.sh/uv/) installed (`brew install uv`)
- `gh` CLI authenticated (`gh auth status`)
- Your GitHub account has push access to the trust repo (or ability to open PRs)

### 1. Setup (one-time)

```bash
uv run scripts/setup.py \
  --username YOUR_GITHUB_USERNAME \
  --email you@example.com \
  --trust ../trust
```

This:
- generates `~/.config/pd/private-key.pem` (RSA 2048)
- creates a CSR and copies it to `../trust/pki/csrs/YOUR_GITHUB_USERNAME.csr`
- writes `~/.config/pd/signer.conf` with your defaults

### 2. Get your certificate signed

```bash
cd ../trust
git add pki/csrs/YOUR_GITHUB_USERNAME.csr
git commit -m "feat: add CSR for YOUR_GITHUB_USERNAME"
git push

gh workflow run pki-issue.yml \
  -f issuer=felixboehm \
  -f csr_path=pki/csrs/YOUR_GITHUB_USERNAME.csr

# Wait for workflow, approve the pki-felixboehm environment gate
# in GitHub's UI, then merge the resulting cert PR.

git pull  # get the new cert
cd ../pd
```

### 3. Create your signature image

```bash
# Sign any PDF in macOS Preview (Tools > Annotate > Signature), save it
uv run scripts/extract-signature.py ~/Desktop/signed-in-preview.pdf
# → writes ~/.config/pd/signature.png
```

### 4. Harden the local key (Touch ID integration)

```bash
./scripts/harden-signing.sh
```

- Suggests a strong passphrase (43 chars, copies to clipboard)
- Save it in your password manager
- Encrypts the private key with AES-256 / 600k PBKDF2
- Stores the passphrase in the macOS Keychain
- Every future signing: macOS prompts for authentication (Touch ID if enabled system-wide)

### 5. Sign the test document

```bash
uv run scripts/sign.py test.pdf
# → creates test_<your-username>.pdf
```

macOS prompts for authentication. Once approved, the signed PDF appears next to the original.

### 6. Verify

```bash
uv run scripts/verify.py test_<your-username>.pdf --trust ../trust
```

Expected output:
```
Found 1 signature(s):
  [PASS] PDSign
    Signer:     Common Name: <your-username>, ...
    Issuer:     Common Name: Performance Dudes Issuing CA - ...
    Intact:     True
    Valid:      True
    Trusted:    True
```

### 7. Open in Adobe Acrobat Reader (optional)

```bash
open -a "Adobe Acrobat Reader" test_<your-username>.pdf
```

Acrobat shows a blue banner at the top with signature status. The first time, it shows "validity unknown" because the Root CA is not in Adobe's trust store — click the signature, navigate to the Root CA certificate, and trust it once. Subsequent signed documents show as fully trusted.

---

## Daily usage

```bash
# Sign any PDF (output: <filename>_<your-username>.pdf)
uv run scripts/sign.py contract.pdf

# Multiple signers chain via filename
uv run scripts/sign.py contract.pdf                  # → contract_felixboehm.pdf
# send contract_felixboehm.pdf to your co-signer
# they run on their machine:
uv run scripts/sign.py contract_felixboehm.pdf       # → contract_felixboehm_nantero1.pdf

# Verify
uv run scripts/verify.py contract_felixboehm_nantero1.pdf --trust ../trust
```

## Rotating the passphrase

```bash
./scripts/harden-signing.sh
# Detects key is already encrypted → interactive menu:
#   [r] Rotate passphrase
#   [s] Re-store current passphrase in Keychain
#   [q] Quit
```

## Configuration

All configuration in `~/.config/pd/signer.conf` (plain `key=value`):

```
github_username=felixboehm
email=felix@performance-dudes.de
org=Performance Dudes
trust_repo=/Users/felix/work/performance-dudes/trust
signature_path=/Users/felix/.config/pd/signature.png
keychain_account=felixboehm
```

Scripts read these as defaults; every option can be overridden on the command line.

---

## Files

```
~/.config/pd/
├── private-key.pem     # Your signing key (encrypted after harden-signing.sh)
├── signing.csr          # Your CSR (once submitted to trust, no longer needed)
├── signature.png        # Your handwritten signature image
└── signer.conf          # Configuration
```

## Install as Claude Code Plugin

```bash
claude plugin marketplace add performance-dudes/pd
claude plugin install pd@pd
```

## Architecture

Three repos work together:

| Repo | Visibility | Contents |
|---|---|---|
| [`performance-dudes/pd`](https://github.com/performance-dudes/pd) (this repo) | public | Signing/verification scripts and Claude skills |
| [`performance-dudes/trust`](https://github.com/performance-dudes/trust) | public | PKI workflows, public certs, trust chain |
| [`performance-dudes/trust-keys`](https://github.com/performance-dudes/trust-keys) | private | Encrypted CA key audit trail |

## Roadmap

- [#1](https://github.com/performance-dudes/pd/issues/1) Pluggable signer backends (Secure Enclave, YubiKey/PKCS#11)
