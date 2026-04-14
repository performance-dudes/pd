# /// script
# dependencies = []
# requires-python = ">=3.10"
# ///
"""Set up local signing environment.

Usage:
    uv run scripts/setup.py --username <github-username> --email <email> [--trust <trust-repo-path>]

Generates a key pair, creates a CSR, and writes signer config.
The CSR must then be submitted to the trust repo and signed via pki-issue.

Config is merged: existing keys in ~/.config/pd/signer.conf are preserved
unless overwritten by a new value. Comments and unknown keys are kept.

Examples:
    uv run scripts/setup.py --username felixboehm --email felix@performance-dudes.de
    uv run scripts/setup.py --username felixboehm --email felix@performance-dudes.de --trust ../trust
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "pd"
CONFIG_FILE = CONFIG_DIR / "signer.conf"


def read_config() -> dict[str, str]:
    """Read key=value pairs from signer.conf."""
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
    """Merge updates into signer.conf, preserving existing keys."""
    current = read_config()
    current.update(updates)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in current.items()]
    CONFIG_FILE.write_text("\n".join(lines) + "\n")
    CONFIG_FILE.chmod(0o600)


def main() -> None:
    parser = argparse.ArgumentParser(description="Set up local signing environment")
    parser.add_argument("--username", required=True, help="Your GitHub username")
    parser.add_argument("--email", required=True, help="Your email address")
    parser.add_argument("--org", default="Performance Dudes", help="Organization name for cert subject")
    parser.add_argument("--trust", type=Path, help="Path to trust repo (copies CSR there if provided)")
    parser.add_argument("--bits", type=int, default=4096,
                        help="RSA key size in bits (default: 4096). 3072 is the BSI minimum for long-term signing; "
                             "4096 is the PD default for durable signatures with classical-security margin.")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing key + CSR (e.g., when upgrading key size).")
    args = parser.parse_args()

    key_path = CONFIG_DIR / "private-key.pem"
    csr_path = CONFIG_DIR / "signing.csr"

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Generate key pair
    if key_path.exists() and not args.force:
        print(f"Private key already exists: {key_path}")
        print("  Use --force to regenerate (e.g., to upgrade key size).")
    else:
        if key_path.exists():
            print(f"Overwriting existing key at {key_path} (--force).")
        subprocess.run([
            "openssl", "genpkey", "-algorithm", "RSA",
            "-pkeyopt", f"rsa_keygen_bits:{args.bits}",
            "-out", str(key_path),
        ], check=True, capture_output=True)
        key_path.chmod(0o600)
        print(f"Generated: {key_path} (RSA-{args.bits})")

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

    # Write / merge config
    updates = {
        "github_username": args.username,
        "email": args.email,
        "org": args.org,
    }
    if args.trust:
        updates["trust_repo"] = str(args.trust.resolve())
    update_config(updates)
    print(f"Config updated: {CONFIG_FILE}")
    for k, v in updates.items():
        print(f"  {k}={v}")

    # Copy CSR to trust repo if provided
    if args.trust:
        csrs_dir = args.trust / "pki" / "csrs"
        csrs_dir.mkdir(parents=True, exist_ok=True)
        dest = csrs_dir / f"{args.username}.csr"
        dest.write_bytes(csr_path.read_bytes())
        print(f"\nCSR copied to: {dest}")
        print("Next steps:")
        print(f"  cd {args.trust}")
        print(f"  git add pki/csrs/{args.username}.csr")
        print(f"  git commit -m 'feat: add CSR for {args.username}'")
        print(f"  git push")
        print(f"  gh workflow run pki-issue.yml -f issuer={args.username} -f csr_path=pki/csrs/{args.username}.csr")
    else:
        print(f"\nNext: copy {csr_path} to the trust repo's pki/csrs/ and trigger pki-issue.")


if __name__ == "__main__":
    main()
