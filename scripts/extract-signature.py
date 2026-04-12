# /// script
# dependencies = [
#   "pikepdf>=9",
#   "Pillow>=10",
# ]
# requires-python = ">=3.10"
# ///
"""Extract a visual signature from a PDF signed in macOS Preview.

Workflow:
    1. Open Preview, create or open any PDF
    2. Tools > Annotate > Signature > add your signature
    3. Save the PDF
    4. Run this script to extract the signature as a transparent PNG

Usage:
    uv run scripts/extract-signature.py <signed-pdf> [--output ~/.config/pd/signature.png]

Examples:
    uv run scripts/extract-signature.py ~/Desktop/signed.pdf
    uv run scripts/extract-signature.py ~/Desktop/signed.pdf --output ~/.config/pd/signature.png
"""

import argparse
import sys
from pathlib import Path

import pikepdf
from PIL import Image
import io


def extract_images_from_pdf(pdf_path: Path) -> list[tuple[bytes, str]]:
    """Extract all images from a PDF, returns list of (image_bytes, format)."""
    images = []
    pdf = pikepdf.Pdf.open(pdf_path)

    for page in pdf.pages:
        if "/Resources" not in page:
            continue
        resources = page["/Resources"]
        if "/XObject" not in resources:
            continue

        xobjects = resources["/XObject"]
        for name, obj in xobjects.items():
            obj = obj.resolve() if hasattr(obj, 'resolve') else obj
            if not hasattr(obj, 'read_bytes'):
                continue
            try:
                image_data = obj.read_bytes()
                width = int(obj.get("/Width", 0))
                height = int(obj.get("/Height", 0))
                if width > 20 and height > 20:  # skip tiny images
                    images.append((image_data, width, height, obj))
            except Exception:
                continue

    pdf.close()
    return images


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract signature image from a PDF")
    parser.add_argument("pdf", type=Path, help="PDF with a signature added in Preview")
    parser.add_argument("--output", type=Path,
                        default=Path.home() / ".config" / "pd" / "signature.png",
                        help="Output PNG path (default: ~/.config/pd/signature.png)")
    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"Error: PDF not found: {args.pdf}", file=sys.stderr)
        sys.exit(1)

    print(f"Extracting images from: {args.pdf}")

    # Use pikepdf to extract images
    pdf = pikepdf.Pdf.open(args.pdf)
    found_images = []

    for page_num, page in enumerate(pdf.pages):
        for image_key, image_obj in page.images.items():
            pdfimage = pikepdf.PdfImage(image_obj)
            try:
                pil_image = pdfimage.as_pil_image()
                w, h = pil_image.size
                if w > 30 and h > 30:
                    found_images.append((pil_image, page_num, image_key, w, h))
            except Exception as e:
                continue

    pdf.close()

    if not found_images:
        print("No images found in the PDF.")
        print("Make sure you added a signature in Preview (Tools > Annotate > Signature).")
        sys.exit(1)

    if len(found_images) == 1:
        img, page, key, w, h = found_images[0]
        print(f"Found 1 image: {w}x{h} on page {page + 1}")
        selected = img
    else:
        print(f"Found {len(found_images)} images:")
        for i, (img, page, key, w, h) in enumerate(found_images):
            print(f"  [{i}] {w}x{h} on page {page + 1}")
        choice = input("Which image is the signature? Enter number: ").strip()
        try:
            selected = found_images[int(choice)][0]
        except (ValueError, IndexError):
            print("Invalid choice.", file=sys.stderr)
            sys.exit(1)

    # Convert to RGBA (transparent background)
    if selected.mode != "RGBA":
        selected = selected.convert("RGBA")

    # Make white/near-white pixels transparent
    data = selected.getdata()
    new_data = []
    for r, g, b, a in data:
        if r > 230 and g > 230 and b > 230:
            new_data.append((r, g, b, 0))  # transparent
        else:
            new_data.append((r, g, b, a))
    selected.putdata(new_data)

    # Save
    args.output.parent.mkdir(parents=True, exist_ok=True)
    selected.save(args.output, "PNG")
    print(f"\nSignature saved: {args.output}")
    print(f"Size: {selected.size[0]}x{selected.size[1]}")
    print(f"\nUse with: uv run scripts/sign.py document.pdf --trust ../trust --signature {args.output}")


if __name__ == "__main__":
    main()
