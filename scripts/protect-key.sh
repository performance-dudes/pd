#!/usr/bin/env bash
#
# Add a passphrase to your unencrypted signing key.
#
# Run this YOURSELF — never let Claude (or any other agent) run it.
# The passphrase you type stays in your terminal session only.
#
# Usage:
#   ./scripts/protect-key.sh
#
# What it does:
#   1. Checks if the key at ~/.config/pd/private-key.pem is already encrypted
#   2. Prompts you for a passphrase (twice to confirm)
#   3. Encrypts the key in place using PKCS#8 v2
#      (AES-256-CBC, HMAC-SHA512 PRF, 600k PBKDF2 iterations)
#
# No unencrypted backup is kept — that would defeat the purpose.
# Ensure the passphrase is stored in your password manager BEFORE running.
#
# After running: sign.py will prompt for the passphrase at signing time.

set -euo pipefail

KEY="${HOME}/.config/pd/private-key.pem"

if [ ! -f "$KEY" ]; then
  echo "Error: no signing key found at $KEY" >&2
  echo "Run scripts/setup.py first to generate one." >&2
  exit 1
fi

TMPDIR="$(mktemp -d)"
# Best-effort wipe of tmpdir contents on exit
cleanup() {
  if [ -d "$TMPDIR" ]; then
    find "$TMPDIR" -type f -exec sh -c '
      for f; do
        if command -v shred >/dev/null 2>&1; then
          shred -u "$f" 2>/dev/null || rm -f "$f"
        else
          dd if=/dev/urandom of="$f" bs=1024 count=4 conv=notrunc 2>/dev/null || true
          rm -f "$f"
        fi
      done
    ' _ {} +
    rm -rf "$TMPDIR"
  fi
}
trap cleanup EXIT

encrypt_in_place() {
  local src="$1"
  echo ""
  echo "Enter the NEW passphrase (AES-256-CBC / HMAC-SHA512 / 600k PBKDF2 iterations):"
  openssl pkcs8 -topk8 -v2 aes-256-cbc -v2prf hmacWithSHA512 -iter 600000 \
    -in "$src" -out "${TMPDIR}/encrypted.pem"
  # Atomically replace
  mv "${TMPDIR}/encrypted.pem" "$KEY"
  chmod 600 "$KEY"
}

# Detect if already encrypted
if grep -q "ENCRYPTED" "$KEY" 2>/dev/null; then
  echo "Key at $KEY is already passphrase-protected."
  read -rp "Replace the existing passphrase? [y/N] " answer
  if [[ ! "$answer" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
  fi

  echo ""
  echo "Enter the CURRENT passphrase:"
  if ! openssl pkey -in "$KEY" -out "${TMPDIR}/unencrypted.pem"; then
    echo "Error: wrong passphrase or decryption failed" >&2
    exit 1
  fi
  encrypt_in_place "${TMPDIR}/unencrypted.pem"
  echo ""
  echo "✓ Passphrase changed."
else
  echo "Key at $KEY is currently NOT encrypted."
  echo ""
  echo "You will be prompted to enter a new passphrase TWICE."
  echo ""
  echo "⚠️  IMPORTANT ⚠️"
  echo "   Save the passphrase in your password manager BEFORE continuing."
  echo "   If you lose it, the key is UNRECOVERABLE."
  echo "   No unencrypted backup will be kept — that is intentional."
  echo ""
  read -rp "Continue? [y/N] " answer
  if [[ ! "$answer" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
  fi

  encrypt_in_place "$KEY"
  echo ""
  echo "✓ Key encrypted in place (no unencrypted backup kept)."
fi

echo "  sign.py will prompt for the passphrase at signing time."
echo ""
echo "Test:"
echo "  uv run scripts/sign.py some.pdf"
