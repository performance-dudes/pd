# /// script
# dependencies = [
#   "pyhanko[opentype]>=0.25",
#   "cryptography>=42",
#   "Pillow>=10",
#   "fpdf2>=2.7",
# ]
# requires-python = ">=3.10"
# ///
"""Sign a PDF with a PKCS#7 digital signature + RFC 3161 timestamp.

By default the signature is cryptographic-only (invisible). Adobe Reader,
macOS Preview, and pyhanko still show it in their signature panel. Use
--visual-signature <name> to additionally embed a handwritten-style
stamp image; omit it for formal documents that already carry an inline
handwritten signature.

Usage:
    uv run scripts/sign.py <pdf> [options]

The signer's private key must be at ~/.config/pd/private-key.pem.
The certificate and chain are read from the trust repo (auto-discovered
from signer.conf, or pass --trust <path>).

Examples:
    uv run scripts/sign.py contract.pdf
    uv run scripts/sign.py contract.pdf --visual-signature                 # uses signer.conf default
    uv run scripts/sign.py contract.pdf --visual-signature alice           # ~/.config/pd/alice.png
    uv run scripts/sign.py contract.pdf --visual-signature any/path/sig.png
    uv run scripts/sign.py contract.pdf --visual-signature alice --box 50,50,250,120
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
    """Convert a PNG signature image to a single-page PDF for use as stamp.

    Preserves the alpha channel: transparent areas in the source PNG remain
    transparent in the resulting stamp PDF, so the signature appears without
    a white box around it when overlaid on a contract.
    """
    from PIL import Image
    from fpdf import FPDF

    img = Image.open(png_path)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    w_px, h_px = img.size
    w_mm = w_px * 25.4 / 150
    h_mm = h_px * 25.4 / 150

    tmp_png = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    img.save(tmp_png.name)

    pdf = FPDF(unit="mm", format=(w_mm, h_mm))
    pdf.set_margin(0)
    pdf.add_page()
    pdf.image(tmp_png.name, x=0, y=0, w=w_mm, h=h_mm)

    tmp_pdf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    pdf.output(tmp_pdf.name)

    os.unlink(tmp_png.name)
    return tmp_pdf.name


_VISUAL_SIG_USE_DEFAULT = "__use_default__"


def _resolve_visual_signature(arg: str | None, conf: dict[str, str]) -> Path | None:
    """Resolve --visual-signature argument to a concrete PNG path.

    - None                  → no visible stamp (cryptographic signature only)
    - "__use_default__"     → flag given without arg, read signer.conf default
    - "<name>"              → ~/.config/pd/<name>.png
    - "<path>" (/ or .png)  → use that path directly
    """
    if arg is None:
        return None
    if arg == _VISUAL_SIG_USE_DEFAULT:
        # Accept legacy `signature_path` for forward-compat with older configs
        saved = conf.get("visual_signature_default") or conf.get("signature_path")
        if not saved:
            print("Error: --visual-signature was passed without a value, but "
                  "signer.conf has no `visual_signature_default`. Either pass "
                  "a name/path, or run `extract-signature.py` to set one.",
                  file=sys.stderr)
            sys.exit(1)
        return Path(saved).expanduser()
    if "/" in arg or arg.lower().endswith(".png"):
        return Path(arg).expanduser()
    return CONFIG_DIR / f"{arg}.png"


def main() -> None:
    conf = read_config()
    default_trust = Path(conf["trust_repo"]).expanduser() if "trust_repo" in conf else None

    parser = argparse.ArgumentParser(
        description="Sign a PDF with your X.509 certificate. "
                    "By default the signature is cryptographic-only (invisible). "
                    "Pass --visual-signature <name> to embed a visible stamp image too.")
    parser.add_argument("pdf", type=Path, help="PDF file to sign (modified in-place)")
    parser.add_argument("--trust", type=Path, default=default_trust,
                        help=f"Path to the trust repo (default: trust_repo from signer.conf, "
                             f"current: {default_trust})")
    parser.add_argument("--username", help="GitHub username (auto-detected from signer.conf)")
    parser.add_argument("--key", type=Path, default=Path.home() / ".config" / "pd" / "private-key.pem",
                        help="Private key path (default: ~/.config/pd/private-key.pem)")
    parser.add_argument("--visual-signature", dest="visual_signature",
                        nargs="?", const=_VISUAL_SIG_USE_DEFAULT, default=None,
                        metavar="NAME-OR-PATH",
                        help="Embed a visible signature stamp. Without a value, uses "
                             "`visual_signature_default` from signer.conf (set by "
                             "extract-signature.py). With a name, uses ~/.config/pd/<name>.png. "
                             "With a path (containing / or ending in .png), uses that file. "
                             "Omit this flag entirely for cryptographic-only signing — the "
                             "PKCS#7 signature + RFC 3161 timestamp are always embedded.")
    parser.add_argument("--output", "-o", type=Path,
                        help="Output path. Default: <input_stem>_<username>.pdf "
                             "(chaining signers, e.g. contract_alice_bob.pdf)")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite output file if it exists")
    parser.add_argument("--field", default="PDSign", help="Signature field name (default: PDSign)")
    parser.add_argument("--reason", default="Document authenticity", help="Signing reason")
    parser.add_argument("--location", default="Performance Dudes", help="Signing location")
    parser.add_argument("--page", type=int, default=0, help="Page for visible signature (0-indexed, default: 0)")
    parser.add_argument("--box", help="Signature box: x1,y1,x2,y2 in points (default: 350,50,550,120)")
    parser.add_argument("--tsa", default="http://timestamp.digicert.com",
                        help="RFC 3161 trusted-timestamp URL (default: DigiCert public TSA). "
                             "The timestamp proves the signature existed at time T from an independent "
                             "trust anchor. Adobe Reader and pyHanko verify it automatically.")
    parser.add_argument("--no-tsa", action="store_true",
                        help="Skip the trusted timestamp (offline signing). NOT recommended for "
                             "durable documents — the timestamp is a major part of long-term "
                             "signature validity.")
    args = parser.parse_args()

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

    # Build visual stamp if --visual-signature was given
    stamp_style = None
    field_spec = None
    stamp_pdf_path = None
    visual_sig_path = _resolve_visual_signature(args.visual_signature, conf)

    if visual_sig_path is not None:
        if not visual_sig_path.exists():
            print(f"Error: Visual signature image not found: {visual_sig_path}", file=sys.stderr)
            sys.exit(1)

        stamp_pdf_path = png_to_stamp_pdf(visual_sig_path)
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

    timestamper = None
    if not args.no_tsa:
        from pyhanko.sign.timestamps import HTTPTimeStamper
        timestamper = HTTPTimeStamper(args.tsa)

    pdf_signer = signers.PdfSigner(
        signature_meta=meta,
        signer=signer,
        stamp_style=stamp_style,
        new_field_spec=field_spec,
        timestamper=timestamper,
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
    if visual_sig_path is not None:
        print(f"  Stamp:     {visual_sig_path}")
    else:
        print(f"  Stamp:     (none — cryptographic-only)")


if __name__ == "__main__":
    main()
