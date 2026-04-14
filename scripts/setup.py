# /// script
# dependencies = []
# requires-python = ">=3.10"
# ///
"""Set up local signing environment.

Usage:
    uv run scripts/setup.py --username <github-username> --email <email>

Generates a key pair (RSA-4096 by default), creates a CSR, writes signer
config, and copies the CSR into the trust repo's pki/csrs/. The trust
repo is auto-discovered (from signer.conf or the pd sibling layout);
pass --trust <path> to override or --no-trust-copy to skip the copy.

Config is merged: existing keys in ~/.config/pd/signer.conf are preserved
unless overwritten by a new value. Comments and unknown keys are kept.

Examples:
    uv run scripts/setup.py --username felixboehm --email felix@performance-dudes.de
    uv run scripts/setup.py --username felixboehm --email felix@performance-dudes.de --force --bits 4096
    uv run scripts/setup.py --username felixboehm --email felix@performance-dudes.de --trust /custom/path
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "pd"
CONFIG_FILE = CONFIG_DIR / "signer.conf"


def _discover_trust_repo() -> Path | None:
    """Find a clone of performance-dudes/trust without requiring --trust.

    Search order:
      1. trust_repo value previously saved in signer.conf
      2. ../trust relative to this script's pd repo (performance-dudes/{pd,trust} sibling layout)

    A candidate is accepted if the directory exists and is a git repo.
    """
    cfg = read_config()
    if saved := cfg.get("trust_repo"):
        p = Path(saved).expanduser()
        if (p / ".git").exists():
            return p

    pd_repo_root = Path(__file__).resolve().parent.parent
    sibling = pd_repo_root.parent / "trust"
    if (sibling / ".git").exists():
        return sibling

    return None


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
    parser.add_argument("--trust", type=Path,
                        help="Path to trust repo. Default: auto-discovered from signer.conf, then from "
                             "the pd repo's sibling at ../trust. Pass --no-trust-copy to skip the CSR copy.")
    parser.add_argument("--no-trust-copy", action="store_true",
                        help="Skip copying the CSR into the trust repo (rarely needed; default is to copy).")
    parser.add_argument("--bits", type=int, default=4096,
                        help="RSA key size in bits (default: 4096). 3072 is the BSI minimum for long-term signing; "
                             "4096 is the PD default for durable signatures with classical-security margin.")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing key + CSR (e.g., when upgrading key size).")
    args = parser.parse_args()

    # Discover trust repo if not passed explicitly
    if args.trust is None and not args.no_trust_copy:
        args.trust = _discover_trust_repo()

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

    # Copy CSR into the trust repo (always, unless --no-trust-copy)
    if args.trust and not args.no_trust_copy:
        csrs_dir = args.trust / "pki" / "csrs"
        csrs_dir.mkdir(parents=True, exist_ok=True)
        dest = csrs_dir / f"{args.username}.csr"
        dest.write_bytes(csr_path.read_bytes())
        print(f"\nCSR copied to: {dest}")
        print("Next steps:")
        print(f"  cd {args.trust}")
        print(f"  git checkout -b pki/csr-{args.username} && git add pki/csrs/{args.username}.csr")
        print(f"  git commit -m 'feat: add CSR for {args.username}' && git push -u origin HEAD")
        print(f"  gh pr create --fill  # get it merged first")
        print(f"  gh workflow run pki-issue.yml -f issuer={args.username} -f csr_path=pki/csrs/{args.username}.csr")
    elif args.no_trust_copy:
        print(f"\n--no-trust-copy set. Copy {csr_path} to the trust repo yourself when ready.")
    else:
        print(f"\nCould not auto-discover a trust repo clone.")
        print(f"  Checked: signer.conf trust_repo + {Path(__file__).resolve().parent.parent.parent / 'trust'}")
        print(f"  Pass --trust <path> or clone performance-dudes/trust as a sibling of pd.")


if __name__ == "__main__":
    main()
