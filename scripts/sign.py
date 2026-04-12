# /// script
# dependencies = [
#   "pyhanko[opentype]>=0.25",
#   "cryptography>=42",
# ]
# requires-python = ">=3.10"
# ///
"""Sign a PDF with a PKCS#7 digital signature.

Usage:
    uv run scripts/sign.py <pdf> --trust <trust-repo-path> [--username <github-username>]

The signer's private key must be at ~/.config/pd/private-key.pem.
The certificate and chain are read from the trust repo.

Examples:
    uv run scripts/sign.py contract.pdf --trust ../trust
    uv run scripts/sign.py contract.pdf --trust ../trust --username felixboehm
    uv run scripts/sign.py contract.pdf --trust ../trust --field SigFelix --reason "Contract approval"
"""

import argparse
import os
import sys
from pathlib import Path

from pyhanko.sign import signers
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter


def find_username(trust_path: Path) -> str | None:
    """Try to detect username from signer.conf or available certs."""
    conf = Path.home() / ".config" / "pd" / "signer.conf"
    if conf.exists():
        for line in conf.read_text().splitlines():
            if line.startswith("github_username="):
                return line.split("=", 1)[1].strip()

    # Fallback: look for certs in the trust repo
    certs_dir = trust_path / "pki" / "certs"
    if certs_dir.exists():
        pems = list(certs_dir.glob("*.pem"))
        if len(pems) == 1:
            return pems[0].stem
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Sign a PDF with your X.509 certificate")
    parser.add_argument("pdf", type=Path, help="PDF file to sign (modified in-place)")
    parser.add_argument("--trust", type=Path, required=True, help="Path to the trust repo")
    parser.add_argument("--username", help="GitHub username (auto-detected from ~/.config/pd/signer.conf)")
    parser.add_argument("--key", type=Path, default=Path.home() / ".config" / "pd" / "private-key.pem",
                        help="Private key path (default: ~/.config/pd/private-key.pem)")
    parser.add_argument("--field", default="PDSign", help="Signature field name (default: PDSign)")
    parser.add_argument("--reason", default="Document authenticity", help="Signing reason")
    parser.add_argument("--location", default="Performance Dudes", help="Signing location")
    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"Error: PDF not found: {args.pdf}", file=sys.stderr)
        sys.exit(1)

    if not args.key.exists():
        print(f"Error: Private key not found: {args.key}", file=sys.stderr)
        print("Run /pd:setup-signing first.", file=sys.stderr)
        sys.exit(1)

    username = args.username or find_username(args.trust)
    if not username:
        print("Error: Could not determine username. Use --username or create ~/.config/pd/signer.conf", file=sys.stderr)
        sys.exit(1)

    cert_path = args.trust / "pki" / "certs" / f"{username}.pem"
    issuer_cert = args.trust / "pki" / "issuers" / username / "issuing-cert.pem"
    root_cert = args.trust / "pki" / "root" / "ca-cert.pem"

    for path, desc in [(cert_path, "Certificate"), (issuer_cert, "Issuing CA cert"), (root_cert, "Root CA cert")]:
        if not path.exists():
            print(f"Error: {desc} not found: {path}", file=sys.stderr)
            sys.exit(1)

    signer = signers.SimpleSigner.load(
        str(args.key),
        str(cert_path),
        ca_chain_files=[str(issuer_cert), str(root_cert)],
        key_passphrase=None,
    )

    with open(args.pdf, "rb") as f:
        w = IncrementalPdfFileWriter(f)
        out = signers.sign_pdf(
            w,
            signers.PdfSignatureMetadata(
                field_name=args.field,
                reason=args.reason,
                location=args.location,
            ),
            signer=signer,
        )
        with open(args.pdf, "wb") as out_f:
            out_f.write(out.getbuffer())

    print(f"Signed: {args.pdf}")
    print(f"  Signer:  {username}")
    print(f"  Field:   {args.field}")
    print(f"  Reason:  {args.reason}")


if __name__ == "__main__":
    main()
