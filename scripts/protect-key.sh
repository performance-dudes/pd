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
#   2. If not, prompts you for a passphrase (twice to confirm)
#   3. Creates a backup at ~/.config/pd/private-key.pem.bak
#   4. Replaces the key with a PKCS#8 encrypted version
#      (AES-256-CBC, HMAC-SHA512 PRF, 600k PBKDF2 iterations)
#
# After running: sign.py will prompt for the passphrase at signing time.

set -euo pipefail

KEY="${HOME}/.config/pd/private-key.pem"
BACKUP="${HOME}/.config/pd/private-key.pem.bak"

if [ ! -f "$KEY" ]; then
  echo "Error: no signing key found at $KEY" >&2
  echo "Run scripts/setup.py first to generate one." >&2
  exit 1
fi

# Detect if already encrypted
if grep -q "ENCRYPTED" "$KEY" 2>/dev/null; then
  echo "Key at $KEY is already passphrase-protected."
  read -rp "Replace the existing passphrase? [y/N] " answer
  if [[ ! "$answer" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
  fi

  # Decrypt with current passphrase, then re-encrypt with new one
  echo ""
  echo "Enter the CURRENT passphrase:"
  TMPDIR="$(mktemp -d)"
  trap 'rm -rf "$TMPDIR"' EXIT

  if ! openssl pkey -in "$KEY" -out "${TMPDIR}/unencrypted.pem"; then
    echo "Error: wrong passphrase or decryption failed" >&2
    exit 1
  fi

  cp "$KEY" "$BACKUP"
  echo ""
  echo "Enter the NEW passphrase (AES-256-CBC, HMAC-SHA512, 600k PBKDF2 iterations):"
  openssl pkcs8 -topk8 -v2 aes-256-cbc -v2prf hmacWithSHA512 -iter 600000 \
    -in "${TMPDIR}/unencrypted.pem" -out "$KEY"
  chmod 600 "$KEY"
  echo ""
  echo "✓ Passphrase changed (AES-256-CBC / HMAC-SHA512 / 600k iterations)."
  echo "  Backup of previous encrypted key: $BACKUP"
else
  echo "Key at $KEY is currently NOT encrypted."
  echo ""
  echo "You will be prompted to enter a new passphrase TWICE."
  echo "⚠️  Save it in your password manager BEFORE continuing."
  echo "   If you lose the passphrase, the key is unrecoverable."
  echo ""
  read -rp "Continue? [y/N] " answer
  if [[ ! "$answer" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
  fi

  # Backup the unencrypted key first (so the user can recover if they lose the passphrase)
  cp "$KEY" "$BACKUP"
  chmod 600 "$BACKUP"
  echo ""
  echo "Backup created: $BACKUP"
  echo "(⚠️  delete this once you've confirmed the encrypted key works)"
  echo ""

  echo "Enter the NEW passphrase:"
  TMPDIR="$(mktemp -d)"
  trap 'rm -rf "$TMPDIR"' EXIT

  # PKCS#8 v2 with AES-256-CBC, HMAC-SHA512 PRF, 600k PBKDF2 iterations
  openssl pkcs8 -topk8 -v2 aes-256-cbc -v2prf hmacWithSHA512 -iter 600000 \
    -in "$KEY" -out "${TMPDIR}/encrypted.pem"
  mv "${TMPDIR}/encrypted.pem" "$KEY"
  chmod 600 "$KEY"

  echo ""
  echo "✓ Key is now encrypted (AES-256-CBC / HMAC-SHA512 / 600k PBKDF2 iterations)."
  echo "  sign.py will prompt for the passphrase at signing time."
  echo ""
  echo "Test it:"
  echo "  uv run scripts/sign.py some.pdf --trust ../trust"
  echo ""
  echo "Once verified, delete the unencrypted backup:"
  echo "  shred -u $BACKUP    # or: rm $BACKUP"
fi
