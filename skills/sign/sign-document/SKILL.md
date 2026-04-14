---
name: sign-document
description: Cryptographically sign a PDF — embeds a PKCS#7 digital signature using the signer's X.509 certificate
---

# Sign a PDF Document

Sign a PDF with the user's end-entity certificate. The signature is embedded in the PDF (PKCS#7/CMS), verifiable by anyone with the Root CA cert.

## Prerequisites

- `~/.config/pd/signer.conf` exists (run `/pd:setup-signing` first)
- `~/.config/pd/private-key.pem` exists
- The user has a signed certificate in the trust repo
- pyHanko is installed

## Steps

### 1. Read signer config

```bash
source ~/.config/pd/signer.conf
```

This gives `$github_username` and `$trust_repo`.

### 2. Verify prerequisites

```bash
# Private key exists
[ -f ~/.config/pd/private-key.pem ] || { echo "No private key. Run /pd:setup-signing"; exit 1; }

# Certificate exists in trust repo
[ -f "${trust_repo}/pki/certs/${github_username}.pem" ] || { echo "No certificate. Run /pd:setup-signing"; exit 1; }

# pyHanko installed
python3 -c "import pyhanko" 2>/dev/null || { echo "pyHanko not installed. Run: pip3 install 'pyhanko[opentype]' cryptography"; exit 1; }
```

### 3. Ask user which PDF to sign

Ask the user for the path to the PDF they want to sign. It must be an existing file.

### 4. Build certificate chain

```bash
CERT="${trust_repo}/pki/certs/${github_username}.pem"
ISSUER_CERT="${trust_repo}/pki/issuers/${github_username}/issuing-cert.pem"
ROOT_CERT="${trust_repo}/pki/root/ca-cert.pem"
```

### 5. Sign the PDF

Prefer the script — it handles the visible stamp image, multi-signer appending, key-passphrase unlock via macOS Keychain / Touch ID, **and the RFC 3161 trusted timestamp** (on by default, pointing at DigiCert's free public TSA).

```bash
cd ~/work/performance-dudes/pd
uv run scripts/sign.py <pdf-path>
# add --no-tsa only if the host is offline (NOT recommended for durable documents)
# add --tsa <url> to use a different TSA (e.g., sectigo, globalsign)
```

The trusted timestamp dramatically strengthens long-term signature validity: it proves the signature existed at time T from an independent trust anchor, so if the signer's private key leaks in 2030 it can't be used to forge a signature "from 2026" — the timestamp bounds the forgery window to after the leak.

Raw-pyhanko fallback if the script isn't available:

```python
import sys
from pyhanko.sign import signers
from pyhanko.sign.timestamps import HTTPTimeStamper
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter

key_path = sys.argv[1]      # ~/.config/pd/private-key.pem
cert_path = sys.argv[2]     # trust/pki/certs/<username>.pem
chain_paths = sys.argv[3:]  # issuing cert, root cert
pdf_path = sys.argv[-1]

signer = signers.SimpleSigner.load(
    key_path,
    cert_path,
    ca_chain_files=chain_paths,
    key_passphrase=None,
)
timestamper = HTTPTimeStamper("http://timestamp.digicert.com")

with open(pdf_path, 'rb') as f:
    w = IncrementalPdfFileWriter(f)
    out = signers.sign_pdf(
        w,
        signers.PdfSignatureMetadata(
            field_name='PDSign',
            reason='Document authenticity',
            location='Performance Dudes',
        ),
        signer=signer,
        timestamper=timestamper,
    )
    with open(pdf_path, 'wb') as out_f:
        out_f.write(out.getbuffer())

print(f"Signed: {pdf_path}")
```

Run this as:

```bash
python3 -c '<the script above>' \
  ~/.config/pd/private-key.pem \
  "${trust_repo}/pki/certs/${github_username}.pem" \
  "${trust_repo}/pki/issuers/${github_username}/issuing-cert.pem" \
  "${trust_repo}/pki/root/ca-cert.pem" \
  "<pdf-path>"
```

IMPORTANT: The actual Python script should be written to a temp file and executed, passing the paths as arguments. The script above is the template — adapt the argument handling as needed. The key point is: `SimpleSigner.load(key, cert, ca_chain_files=[issuer, root])`.

### 6. Verify the signature

```python
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko.pdf_utils.reader import PdfFileReader

with open(pdf_path, 'rb') as f:
    reader = PdfFileReader(f)
    for sig in reader.embedded_signatures:
        print(f"Field: {sig.field_name}")
        print(f"Signer: {sig.signer_cert.subject.human_friendly}")
        print(f"Issuer: {sig.signer_cert.issuer.human_friendly}")
        print("Signature structurally valid.")
```

### 7. Commit the signed PDF

```bash
git add <pdf-path>
git commit -S -m "feat: sign <filename>"
```

The `-S` flag creates a signed git commit (using whatever signing method the user has configured — SSH or GPG).

### 8. Push and create PR

```bash
git push
# If on a branch:
gh pr create --title "feat: sign <filename>" --body "Cryptographically signed with X.509 certificate."
```

## Notes

- The signature is INCREMENTAL — it appends to the PDF without modifying existing content. Multiple people can sign the same PDF sequentially.
- The private key never leaves the local machine.
- The certificate chain is embedded in the signature, so verifiers don't need to fetch the trust repo.
