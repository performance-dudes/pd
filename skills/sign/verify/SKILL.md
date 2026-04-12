---
name: verify
description: Verify a cryptographic PDF signature against the trust repo's Root CA
---

# Verify a PDF Signature

Check if a PDF has a valid cryptographic signature and trace it to the Root CA.

## Steps

### 1. Check if pyHanko is installed

```bash
python3 -c "import pyhanko" 2>/dev/null || { echo "Install: pip3 install 'pyhanko[opentype]' cryptography"; exit 1; }
```

### 2. Ask the user which PDF to verify

### 3. List all signatures in the PDF

```python
import sys
from pyhanko.pdf_utils.reader import PdfFileReader

pdf_path = sys.argv[1]

with open(pdf_path, 'rb') as f:
    reader = PdfFileReader(f)
    sigs = list(reader.embedded_signatures)
    if not sigs:
        print("No digital signatures found in this PDF.")
        sys.exit(0)
    for sig in sigs:
        print(f"Field: {sig.field_name}")
        print(f"Signer: {sig.signer_cert.subject.human_friendly}")
        print(f"Issuer: {sig.signer_cert.issuer.human_friendly}")
        print(f"Not before: {sig.signer_cert.not_valid_before}")
        print(f"Not after:  {sig.signer_cert.not_valid_after}")
        print()
```

### 4. Report findings

Tell the user:
- How many signatures the PDF has
- Who signed it (CN from the certificate)
- Which Issuing CA issued the certificate
- Whether the cert chains to the Performance Dudes Root CA
