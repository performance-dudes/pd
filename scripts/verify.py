# /// script
# dependencies = [
#   "pyhanko[opentype]>=0.25",
#   "cryptography>=42",
#   "pyhanko-certvalidator>=0.26",
# ]
# requires-python = ">=3.10"
# ///
"""Verify digital signatures in a PDF.

Usage:
    uv run scripts/verify.py <pdf> [--trust <trust-repo-path>]

Without --trust: lists signatures and their details.
With --trust: also validates the chain against the Root CA.

Examples:
    uv run scripts/verify.py contract.pdf
    uv run scripts/verify.py contract.pdf --trust ../trust
"""

import argparse
import sys
from pathlib import Path

from pyhanko.pdf_utils.reader import PdfFileReader


def list_signatures(pdf_path: Path) -> None:
    """List all signatures in a PDF."""
    with open(pdf_path, "rb") as f:
        reader = PdfFileReader(f)
        sigs = list(reader.embedded_signatures)

        if not sigs:
            print("No digital signatures found.")
            return

        print(f"Found {len(sigs)} signature(s):\n")
        for sig in sigs:
            cert = sig.signer_cert
            print(f"  Field:      {sig.field_name}")
            print(f"  Signer:     {cert.subject.human_friendly}")
            print(f"  Issuer:     {cert.issuer.human_friendly}")
            print(f"  Valid from: {cert.not_valid_before}")
            print(f"  Valid to:   {cert.not_valid_after}")
            print()


def validate_signatures(pdf_path: Path, trust_path: Path) -> bool:
    """Validate signatures against the trust repo's Root CA."""
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext
    from asn1crypto import pem, x509

    root_pem = trust_path / "pki" / "root" / "ca-cert.pem"
    if not root_pem.exists():
        print(f"Error: Root CA cert not found: {root_pem}", file=sys.stderr)
        return False

    with open(root_pem, "rb") as f:
        _, _, der = pem.unarmor(f.read())
        root = x509.Certificate.load(der)

    vc = ValidationContext(trust_roots=[root])
    all_valid = True

    with open(pdf_path, "rb") as f:
        reader = PdfFileReader(f)
        sigs = list(reader.embedded_signatures)

        if not sigs:
            print("No digital signatures found.")
            return False

        print(f"Found {len(sigs)} signature(s):\n")
        for sig in sigs:
            status = validate_pdf_signature(sig, vc)
            ok = "PASS" if status.bottom_line else "FAIL"
            print(f"  [{ok}] {sig.field_name}")
            print(f"    Signer:     {status.signing_cert.subject.human_friendly}")
            print(f"    Issuer:     {status.signing_cert.issuer.human_friendly}")
            print(f"    Intact:     {status.intact}")
            print(f"    Valid:      {status.valid}")
            print(f"    Trusted:    {status.trusted}")
            print()
            if not status.bottom_line:
                all_valid = False

    return all_valid


def read_trust_from_config() -> Path | None:
    """Read trust_repo= from ~/.config/pd/signer.conf."""
    conf = Path.home() / ".config" / "pd" / "signer.conf"
    if not conf.exists():
        return None
    for line in conf.read_text().splitlines():
        line = line.strip()
        if line.startswith("trust_repo="):
            return Path(line.split("=", 1)[1].strip()).expanduser()
    return None


def main() -> None:
    default_trust = read_trust_from_config()
    parser = argparse.ArgumentParser(description="Verify PDF digital signatures")
    parser.add_argument("pdf", type=Path, help="PDF file to verify")
    parser.add_argument("--trust", type=Path, default=default_trust,
                        help=f"Path to trust repo (default: trust_repo from signer.conf, "
                             f"current: {default_trust})")
    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"Error: PDF not found: {args.pdf}", file=sys.stderr)
        sys.exit(1)

    if args.trust:
        ok = validate_signatures(args.pdf, args.trust)
        sys.exit(0 if ok else 1)
    else:
        list_signatures(args.pdf)


if __name__ == "__main__":
    main()
