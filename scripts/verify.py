# /// script
# dependencies = [
#   "pyhanko[opentype]>=0.25",
#   "cryptography>=42",
#   "pyhanko-certvalidator>=0.26",
#   "certifi>=2024.2.2",
# ]
# requires-python = ">=3.10"
# ///
"""Verify digital signatures in a PDF.

Usage:
    uv run scripts/verify.py <pdf> [--trust <trust-repo-path>]

Signer chain is validated against the PD Root CA (from --trust or
signer.conf). Timestamp chain is validated against the public Mozilla
CA bundle (certifi) — that's where common TSAs (DigiCert, Sectigo,
GlobalSign) anchor. Both validations run offline: the TSA cert is
embedded in the signature and certifi ships the roots locally.

Without --trust: lists signatures and their details (no validation).

Examples:
    uv run scripts/verify.py contract.pdf
    uv run scripts/verify.py contract.pdf --trust ../trust
"""

import argparse
import sys
from pathlib import Path

from pyhanko.pdf_utils.reader import PdfFileReader


def _load_public_ca_bundle():
    """Load Mozilla's curated CA roots via certifi. Used for TSA chain
    validation — common TSAs (DigiCert, Sectigo, GlobalSign) anchor here."""
    import certifi
    from asn1crypto import pem, x509

    roots = []
    with open(certifi.where(), "rb") as f:
        data = f.read()
    for type_name, _headers, der in pem.unarmor(data, multiple=True):
        if type_name == "CERTIFICATE":
            roots.append(x509.Certificate.load(der))
    return roots


def list_signatures(pdf_path: Path) -> None:
    """List all signatures in a PDF without cryptographic validation."""
    with open(pdf_path, "rb") as f:
        reader = PdfFileReader(f)
        sigs = list(reader.embedded_signatures)

        if not sigs:
            print("No digital signatures found.")
            return

        print(f"Found {len(sigs)} signature(s):\n")
        for sig in sigs:
            cert = sig.signer_cert
            has_ts = sig.attached_timestamp_data is not None
            print(f"  Field:      {sig.field_name}")
            print(f"  Signer:     {cert.subject.human_friendly}")
            print(f"  Issuer:     {cert.issuer.human_friendly}")
            print(f"  Valid from: {cert.not_valid_before}")
            print(f"  Valid to:   {cert.not_valid_after}")
            print(f"  Timestamp:  {'attached (RFC 3161)' if has_ts else 'none'}")
            print()


def validate_signatures(pdf_path: Path, trust_path: Path) -> bool:
    """Validate signatures. Signer chain → PD Root. TSA chain → public roots."""
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

    signer_vc = ValidationContext(trust_roots=[root])
    ts_vc = ValidationContext(trust_roots=_load_public_ca_bundle())

    all_valid = True

    with open(pdf_path, "rb") as f:
        reader = PdfFileReader(f)
        sigs = list(reader.embedded_signatures)

        if not sigs:
            print("No digital signatures found.")
            return False

        print(f"Found {len(sigs)} signature(s):\n")
        for sig in sigs:
            status = validate_pdf_signature(
                sig,
                signer_validation_context=signer_vc,
                ts_validation_context=ts_vc,
            )
            ok = "PASS" if status.bottom_line else "FAIL"
            has_ts = sig.attached_timestamp_data is not None
            print(f"  [{ok}] {sig.field_name}")
            print(f"    Signer:     {status.signing_cert.subject.human_friendly}")
            print(f"    Issuer:     {status.signing_cert.issuer.human_friendly}")
            print(f"    Intact:     {status.intact}")
            print(f"    Valid:      {status.valid}")
            print(f"    Trusted:    {status.trusted}")
            if has_ts:
                ts_trusted = (
                    status.timestamp_validity is not None
                    and getattr(status.timestamp_validity, "trusted", False)
                )
                print(f"    Timestamp:  attached, chain trusted: {ts_trusted}")
                if not ts_trusted:
                    all_valid = False
            else:
                print(f"    Timestamp:  none attached")
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
