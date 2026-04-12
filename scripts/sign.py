# /// script
# dependencies = [
#   "pyhanko[opentype]>=0.25",
#   "cryptography>=42",
#   "Pillow>=10",
#   "fpdf2>=2.7",
# ]
# requires-python = ">=3.10"
# ///
"""Sign a PDF with a PKCS#7 digital signature, optionally with a visible signature stamp.

Usage:
    uv run scripts/sign.py <pdf> --trust <trust-repo-path> [options]

The signer's private key must be at ~/.config/pd/private-key.pem.
The certificate and chain are read from the trust repo.

Examples:
    uv run scripts/sign.py contract.pdf --trust ../trust
    uv run scripts/sign.py contract.pdf --trust ../trust --signature ~/.config/pd/signature.png
    uv run scripts/sign.py contract.pdf --trust ../trust --signature ~/.config/pd/signature.png --box 50,50,250,120
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

from pyhanko.sign import signers, fields as sig_fields
from pyhanko.stamp import StaticStampStyle
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.content import ImportedPdfPage


def find_username(trust_path: Path) -> str | None:
    """Try to detect username from signer.conf or available certs."""
    conf = Path.home() / ".config" / "pd" / "signer.conf"
    if conf.exists():
        for line in conf.read_text().splitlines():
            if line.startswith("github_username="):
                return line.split("=", 1)[1].strip()
    certs_dir = trust_path / "pki" / "certs"
    if certs_dir.exists():
        pems = list(certs_dir.glob("*.pem"))
        if len(pems) == 1:
            return pems[0].stem
    return None


def png_to_stamp_pdf(png_path: Path) -> str:
    """Convert a PNG signature image to a single-page PDF for use as stamp background."""
    from PIL import Image
    from fpdf import FPDF

    img = Image.open(png_path).convert("RGB")
    w_px, h_px = img.size
    w_mm = w_px * 25.4 / 150
    h_mm = h_px * 25.4 / 150

    tmp_rgb = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    img.save(tmp_rgb.name)

    pdf = FPDF(unit="mm", format=(w_mm, h_mm))
    pdf.set_margin(0)
    pdf.add_page()
    pdf.image(tmp_rgb.name, x=0, y=0, w=w_mm, h=h_mm)

    tmp_pdf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    pdf.output(tmp_pdf.name)

    os.unlink(tmp_rgb.name)
    return tmp_pdf.name


def main() -> None:
    parser = argparse.ArgumentParser(description="Sign a PDF with your X.509 certificate")
    parser.add_argument("pdf", type=Path, help="PDF file to sign (modified in-place)")
    parser.add_argument("--trust", type=Path, required=True, help="Path to the trust repo")
    parser.add_argument("--username", help="GitHub username (auto-detected from ~/.config/pd/signer.conf)")
    parser.add_argument("--key", type=Path, default=Path.home() / ".config" / "pd" / "private-key.pem",
                        help="Private key path (default: ~/.config/pd/private-key.pem)")
    parser.add_argument("--signature", type=Path, help="Signature image (PNG) for visible stamp")
    parser.add_argument("--field", default="PDSign", help="Signature field name (default: PDSign)")
    parser.add_argument("--reason", default="Document authenticity", help="Signing reason")
    parser.add_argument("--location", default="Performance Dudes", help="Signing location")
    parser.add_argument("--page", type=int, default=0, help="Page for visible signature (0-indexed, default: 0)")
    parser.add_argument("--box", help="Signature box: x1,y1,x2,y2 in points (default: 350,50,550,120)")
    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"Error: PDF not found: {args.pdf}", file=sys.stderr)
        sys.exit(1)

    if not args.key.exists():
        print(f"Error: Private key not found: {args.key}", file=sys.stderr)
        print("Run: uv run scripts/setup.py --help", file=sys.stderr)
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

    # Build visual stamp if signature image provided
    stamp_style = None
    field_spec = None
    stamp_pdf_path = None

    if args.signature:
        if not args.signature.exists():
            print(f"Error: Signature image not found: {args.signature}", file=sys.stderr)
            sys.exit(1)

        stamp_pdf_path = png_to_stamp_pdf(args.signature)
        stamp_style = StaticStampStyle(
            background=ImportedPdfPage(stamp_pdf_path),
            border_width=0,
        )

        if args.box:
            coords = tuple(float(x) for x in args.box.split(","))
        else:
            coords = (350, 50, 550, 120)

        field_spec = sig_fields.SigFieldSpec(
            sig_field_name=args.field,
            on_page=args.page,
            box=coords,
        )

    meta = signers.PdfSignatureMetadata(
        field_name=args.field,
        reason=args.reason,
        location=args.location,
    )

    pdf_signer = signers.PdfSigner(
        signature_meta=meta,
        signer=signer,
        stamp_style=stamp_style,
        new_field_spec=field_spec,
    )

    with open(args.pdf, "rb") as f:
        w = IncrementalPdfFileWriter(f)
        out = pdf_signer.sign_pdf(w)
        with open(args.pdf, "wb") as out_f:
            out_f.write(out.getbuffer())

    # Cleanup temp stamp PDF
    if stamp_pdf_path:
        os.unlink(stamp_pdf_path)

    print(f"Signed: {args.pdf}")
    print(f"  Signer:    {username}")
    print(f"  Field:     {args.field}")
    print(f"  Reason:    {args.reason}")
    if args.signature:
        print(f"  Stamp:     {args.signature}")


if __name__ == "__main__":
    main()
