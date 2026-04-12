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


CONFIG_DIR = Path.home() / ".config" / "pd"
CONFIG_FILE = CONFIG_DIR / "signer.conf"
DEFAULT_SIGNATURE = CONFIG_DIR / "signature.png"


def read_config() -> dict[str, str]:
    """Read key=value pairs from ~/.config/pd/signer.conf."""
    if not CONFIG_FILE.exists():
        return {}
    result = {}
    for line in CONFIG_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        result[k.strip()] = v.strip()
    return result


def find_username(trust_path: Path | None) -> str | None:
    """Try to detect username from signer.conf or available certs."""
    conf = read_config()
    if "github_username" in conf:
        return conf["github_username"]
    if trust_path:
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
    conf = read_config()
    default_trust = Path(conf["trust_repo"]).expanduser() if "trust_repo" in conf else None
    # signature_path in config wins; else fall back to ~/.config/pd/signature.png
    if "signature_path" in conf:
        sig_candidate = Path(conf["signature_path"]).expanduser()
        default_signature = sig_candidate if sig_candidate.exists() else None
    else:
        default_signature = DEFAULT_SIGNATURE if DEFAULT_SIGNATURE.exists() else None
    default_nosig = conf.get("no_signature_by_default", "").lower() in ("1", "true", "yes")

    parser = argparse.ArgumentParser(description="Sign a PDF with your X.509 certificate")
    parser.add_argument("pdf", type=Path, help="PDF file to sign (modified in-place)")
    parser.add_argument("--trust", type=Path, default=default_trust,
                        help=f"Path to the trust repo (default: trust_repo from signer.conf, "
                             f"current: {default_trust})")
    parser.add_argument("--username", help="GitHub username (auto-detected from signer.conf)")
    parser.add_argument("--key", type=Path, default=Path.home() / ".config" / "pd" / "private-key.pem",
                        help="Private key path (default: ~/.config/pd/private-key.pem)")
    parser.add_argument("--signature", type=Path,
                        default=None if default_nosig else default_signature,
                        help=f"Signature image for visible stamp (default: "
                             f"{default_signature or '(none)'})")
    parser.add_argument("--no-signature", action="store_true",
                        help="Sign without visible stamp (overrides default signature)")
    parser.add_argument("--output", "-o", type=Path,
                        help="Output path. Default: <input_stem>_<username>.pdf "
                             "(chaining signers, e.g. contract_felixboehm_nantero1.pdf)")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite output file if it exists")
    parser.add_argument("--field", default="PDSign", help="Signature field name (default: PDSign)")
    parser.add_argument("--reason", default="Document authenticity", help="Signing reason")
    parser.add_argument("--location", default="Performance Dudes", help="Signing location")
    parser.add_argument("--page", type=int, default=0, help="Page for visible signature (0-indexed, default: 0)")
    parser.add_argument("--box", help="Signature box: x1,y1,x2,y2 in points (default: 350,50,550,120)")
    args = parser.parse_args()

    if args.no_signature:
        args.signature = None

    if not args.pdf.exists():
        print(f"Error: PDF not found: {args.pdf}", file=sys.stderr)
        sys.exit(1)

    if not args.trust:
        print("Error: --trust not set and no trust_repo in signer.conf", file=sys.stderr)
        print(f"Add 'trust_repo=/path/to/trust' to {CONFIG_FILE}", file=sys.stderr)
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

    # Detect if the key is encrypted (contains "ENCRYPTED" header line)
    key_text = args.key.read_text()
    key_encrypted = "ENCRYPTED" in key_text

    key_passphrase = None
    if key_encrypted:
        # Try Keychain (pd-keychain helper with Touch ID) first
        keychain_account = conf.get("keychain_account")
        if keychain_account:
            import shutil
            import subprocess
            pdk = shutil.which("pd-keychain") or str(Path.home() / ".local" / "bin" / "pd-keychain")
            if os.path.exists(pdk):
                try:
                    result = subprocess.run(
                        [pdk, "get", keychain_account],
                        capture_output=True,
                        check=False,
                    )
                    if result.returncode == 0 and result.stdout:
                        # Strip any trailing newline that keychain tooling may append
                        key_passphrase = result.stdout.rstrip(b"\n\r")
                    else:
                        stderr = result.stderr.decode("utf-8", errors="replace").strip()
                        print(f"Keychain access failed: {stderr}", file=sys.stderr)
                        print("Falling back to manual passphrase entry...", file=sys.stderr)
                except Exception as e:
                    print(f"Keychain helper error: {e}", file=sys.stderr)

        if key_passphrase is None:
            import getpass
            passphrase = getpass.getpass(f"Passphrase for {args.key}: ")
            if not passphrase:
                print("Error: passphrase required for encrypted key", file=sys.stderr)
                sys.exit(1)
            key_passphrase = passphrase.encode("utf-8")

    try:
        signer = signers.SimpleSigner.load(
            str(args.key),
            str(cert_path),
            ca_chain_files=[str(issuer_cert), str(root_cert)],
            key_passphrase=key_passphrase,
        )
    except Exception as e:
        if key_encrypted:
            print(f"Error loading key (wrong passphrase?): {e}", file=sys.stderr)
        else:
            print(f"Error loading key: {e}", file=sys.stderr)
        sys.exit(1)

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

    # Determine output path: append _<username> to the stem
    if args.output:
        output_path = args.output
    else:
        stem = args.pdf.stem
        # Avoid duplicate suffix if the same user signs twice in a row
        suffix = f"_{username}"
        if stem.endswith(suffix):
            print(f"Error: input filename already ends with '{suffix}'. "
                  f"Use --output to pick a different path or --force.", file=sys.stderr)
            if not args.force:
                sys.exit(1)
            output_path = args.pdf.with_name(f"{stem}{suffix}{args.pdf.suffix}")
        else:
            output_path = args.pdf.with_name(f"{stem}{suffix}{args.pdf.suffix}")

    if output_path.exists() and not args.force:
        print(f"Error: output file exists: {output_path}", file=sys.stderr)
        print("Use --force to overwrite, or --output to choose a different path.", file=sys.stderr)
        sys.exit(1)

    if output_path.resolve() == args.pdf.resolve():
        print(f"Error: output path equals input path: {output_path}", file=sys.stderr)
        sys.exit(1)

    import io
    output_buf = io.BytesIO()
    with open(args.pdf, "rb") as f:
        w = IncrementalPdfFileWriter(f)
        pdf_signer.sign_pdf(w, output=output_buf)
    with open(output_path, "wb") as out_f:
        out_f.write(output_buf.getvalue())

    # Cleanup temp stamp PDF
    if stamp_pdf_path:
        os.unlink(stamp_pdf_path)

    print(f"Signed: {output_path}")
    print(f"  Input:     {args.pdf}")
    print(f"  Signer:    {username}")
    print(f"  Field:     {args.field}")
    print(f"  Reason:    {args.reason}")
    if args.signature:
        print(f"  Stamp:     {args.signature}")


if __name__ == "__main__":
    main()
