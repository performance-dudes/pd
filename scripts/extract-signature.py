# /// script
# dependencies = [
#   "Pillow>=10",
# ]
# requires-python = ">=3.10"
# ///
"""Extract a visual signature from a PDF signed in macOS Preview.

Workflow:
    1. Open any PDF in Preview
    2. Tools > Annotate > Signature > place your signature
    3. Cmd+S to save
    4. Run this script to extract the signature as a transparent PNG

Usage:
    uv run scripts/extract-signature.py <signed-pdf> [--name <name> | --output <path>]

The script renders the PDF at high resolution, detects the signature
region (separated from text by whitespace), crops it, and makes the
background transparent. The saved path is recorded as
`visual_signature_default` in ~/.config/pd/signer.conf, so
`sign.py --visual-signature` (no argument) picks it up automatically.

Examples:
    uv run scripts/extract-signature.py signed.pdf                 # → ~/.config/pd/signature.png
    uv run scripts/extract-signature.py signed.pdf --name formal   # → ~/.config/pd/formal.png
    uv run scripts/extract-signature.py signed.pdf --output ~/path/foo.png
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

CONFIG_DIR = Path.home() / ".config" / "pd"
CONFIG_FILE = CONFIG_DIR / "signer.conf"


def read_config() -> dict[str, str]:
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


def update_config(updates: dict[str, str]) -> None:
    current = read_config()
    current.update(updates)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text("\n".join(f"{k}={v}" for k, v in current.items()) + "\n")
    CONFIG_FILE.chmod(0o600)


def render_pdf_page(pdf_path: Path, size: int = 3000) -> Image.Image:
    """Render a PDF page to PNG using macOS qlmanage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(
            ["qlmanage", "-t", "-s", str(size), "-o", tmpdir, str(pdf_path)],
            capture_output=True,
        )
        # qlmanage outputs as <filename>.png
        for f in os.listdir(tmpdir):
            if f.endswith(".png"):
                return Image.open(os.path.join(tmpdir, f)).convert("RGBA").copy()
    raise RuntimeError("qlmanage failed to render the PDF")


def find_signature_region(img: Image.Image, threshold: int = 235, min_gap: int = 30) -> tuple[int, int, int, int] | None:
    """Find the signature region by detecting a gap between text and signature content."""
    w, h = img.size

    def row_has_content(y: int) -> bool:
        count = 0
        for x in range(w):
            r, g, b, a = img.getpixel((x, y))
            if r < threshold and g < threshold and b < threshold:
                count += 1
                if count >= 5:
                    return True
        return False

    content_rows = [y for y in range(h) if row_has_content(y)]
    if len(content_rows) < 2:
        return None

    # Find gaps between content blocks
    gaps = []
    for i in range(1, len(content_rows)):
        gap = content_rows[i] - content_rows[i - 1]
        if gap > min_gap:
            gaps.append((content_rows[i - 1], content_rows[i]))

    if not gaps:
        return None

    # Signature = everything after the last big gap
    sig_start_y = gaps[-1][1]
    sig_end_y = content_rows[-1]

    # Find column bounds
    min_x, max_x = w, 0
    for y in range(sig_start_y, sig_end_y + 1):
        for x in range(w):
            r, g, b, a = img.getpixel((x, y))
            if r < threshold and g < threshold and b < threshold:
                min_x = min(min_x, x)
                max_x = max(max_x, x)

    if max_x <= min_x:
        return None

    margin = 15
    return (
        max(0, min_x - margin),
        max(0, sig_start_y - margin),
        min(w, max_x + margin),
        min(h, sig_end_y + margin),
    )


def make_background_transparent(img: Image.Image, threshold: int = 235) -> Image.Image:
    """Replace white/near-white pixels with transparency."""
    img = img.convert("RGBA")
    pixels = list(img.getdata())
    new_pixels = [
        (r, g, b, 0) if r > threshold and g > threshold and b > threshold else (r, g, b, 255)
        for r, g, b, a in pixels
    ]
    img.putdata(new_pixels)
    return img


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract signature from a Preview-signed PDF")
    parser.add_argument("pdf", type=Path, help="PDF with a signature added in Preview")
    dest = parser.add_mutually_exclusive_group()
    dest.add_argument("--name", metavar="NAME",
                      help="Save as ~/.config/pd/<NAME>.png (useful for multiple signatures). "
                           "Mutually exclusive with --output.")
    dest.add_argument("--output", type=Path,
                      help="Output PNG path. Mutually exclusive with --name. "
                           "Default (neither given): ~/.config/pd/signature.png")
    parser.add_argument("--resolution", type=int, default=3000,
                        help="Render resolution in pixels (longest edge, default: 3000)")
    args = parser.parse_args()

    if args.name:
        args.output = CONFIG_DIR / f"{args.name}.png"
    elif args.output is None:
        args.output = CONFIG_DIR / "signature.png"

    if not args.pdf.exists():
        print(f"Error: PDF not found: {args.pdf}", file=sys.stderr)
        sys.exit(1)

    if sys.platform != "darwin":
        print("Error: this script uses macOS qlmanage for PDF rendering", file=sys.stderr)
        sys.exit(1)

    print(f"Rendering: {args.pdf}")
    img = render_pdf_page(args.pdf, args.resolution)
    print(f"  Rendered: {img.size[0]}x{img.size[1]}")

    print("Detecting signature region...")
    region = find_signature_region(img)
    if not region:
        print("Error: could not detect signature region.", file=sys.stderr)
        print("Make sure the PDF has text at the top and the signature below,", file=sys.stderr)
        print("separated by whitespace.", file=sys.stderr)
        sys.exit(1)

    x1, y1, x2, y2 = region
    cropped = img.crop(region)
    print(f"  Found: {cropped.size[0]}x{cropped.size[1]} at ({x1},{y1})-({x2},{y2})")

    result = make_background_transparent(cropped)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.save(args.output, "PNG")

    update_config({"visual_signature_default": str(args.output.resolve())})

    print(f"\n✓ Signature saved: {args.output}")
    print(f"  Size: {result.size[0]}x{result.size[1]}")
    print(f"✓ Config updated: visual_signature_default={args.output}")
    print(f"\nUse with: uv run scripts/sign.py document.pdf --visual-signature")
    print(f"(or omit --visual-signature for a cryptographic-only signature)")


if __name__ == "__main__":
    main()
