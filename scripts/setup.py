# /// script
# dependencies = []
# requires-python = ">=3.10"
# ///
"""Set up local signing environment.

Usage:
    uv run scripts/setup.py --username <github-username> --email <email> [--trust <trust-repo-path>]

Generates a key pair, creates a CSR, and writes signer config.
The CSR must then be submitted to the trust repo and signed via pki-issue.

Examples:
    uv run scripts/setup.py --username felixboehm --email felix@performance-dudes.de
    uv run scripts/setup.py --username felixboehm --email felix@performance-dudes.de --trust ../trust
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Set up local signing environment")
    parser.add_argument("--username", required=True, help="Your GitHub username")
    parser.add_argument("--email", required=True, help="Your email address")
    parser.add_argument("--org", default="Performance Dudes", help="Organization name for cert subject")
    parser.add_argument("--trust", type=Path, help="Path to trust repo (copies CSR there if provided)")
    args = parser.parse_args()

    config_dir = Path.home() / ".config" / "pd"
    key_path = config_dir / "private-key.pem"
    csr_path = config_dir / "signing.csr"
    conf_path = config_dir / "signer.conf"

    # Create config directory
    config_dir.mkdir(parents=True, exist_ok=True)

    # Generate key pair (if not exists)
    if key_path.exists():
        print(f"Private key already exists: {key_path}")
    else:
        subprocess.run([
            "openssl", "genpkey", "-algorithm", "RSA",
            "-pkeyopt", "rsa_keygen_bits:2048",
            "-out", str(key_path),
        ], check=True, capture_output=True)
        key_path.chmod(0o600)
        print(f"Generated: {key_path}")

    # Create CSR
    subject = f"/CN={args.username}/emailAddress={args.email}/O={args.org}"
    subprocess.run([
        "openssl", "req", "-new",
        "-key", str(key_path),
        "-out", str(csr_path),
        "-subj", subject,
    ], check=True, capture_output=True)
    print(f"Created CSR: {csr_path}")
    print(f"  Subject: {subject}")

    # Write signer config
    conf_path.write_text(
        f"github_username={args.username}\n"
        f"trust_repo={args.trust or '../trust'}\n"
    )
    print(f"Config: {conf_path}")

    # Copy CSR to trust repo if path provided
    if args.trust:
        csrs_dir = args.trust / "pki" / "csrs"
        csrs_dir.mkdir(parents=True, exist_ok=True)
        dest = csrs_dir / f"{args.username}.csr"
        dest.write_bytes(csr_path.read_bytes())
        print(f"\nCSR copied to: {dest}")
        print(f"Next steps:")
        print(f"  cd {args.trust}")
        print(f"  git add pki/csrs/{args.username}.csr")
        print(f"  git commit -m 'feat: add CSR for {args.username}'")
        print(f"  git push")
        print(f"  gh workflow run pki-issue.yml -f issuer={args.username} -f csr_path=pki/csrs/{args.username}.csr")
    else:
        print(f"\nNext: copy {csr_path} to the trust repo's pki/csrs/ and trigger pki-issue.")


if __name__ == "__main__":
    main()
