#!/usr/bin/env bash
#
# Consolidated setup for secure local signing.
#
# Run this YOURSELF after scripts/setup.py has generated the key.
# Do three things in one flow:
#
#   1. Encrypt the private key at ~/.config/pd/private-key.pem with AES-256
#   2. Compile and install the pd-keychain Swift helper (if needed)
#   3. Store the passphrase in the macOS Keychain with Touch ID enforcement
#
# After this, sign.py will prompt Touch ID instead of asking for the passphrase.
#
# Requires: Xcode Command Line Tools (xcode-select --install)
#
# Portability: Keychain items are device-bound (Touch ID ACL prevents iCloud
# sync by Apple's design). For cross-device use, save the passphrase in your
# password manager (Bitwarden/Vaultwarden). Re-run this script on each Mac.

set -euo pipefail

# ── Paths ────────────────────────────────────────────────────────────────────
CONFIG_DIR="${HOME}/.config/pd"
CONFIG_FILE="${CONFIG_DIR}/signer.conf"
KEY="${CONFIG_DIR}/private-key.pem"
PDK_SRC_REL="tools/pd-keychain.swift"
PDK_DEST="${HOME}/.local/bin/pd-keychain"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PDK_SRC="${REPO_ROOT}/${PDK_SRC_REL}"

# ── Sanity checks ────────────────────────────────────────────────────────────
if [ "$(uname -s)" != "Darwin" ]; then
  echo "Error: this hardening flow is macOS-only (uses Touch ID + Keychain)." >&2
  exit 1
fi

if [ ! -f "$KEY" ]; then
  echo "Error: no signing key at $KEY" >&2
  echo "Run: uv run scripts/setup.py --username <you> --email <you@...> --trust ../trust" >&2
  exit 1
fi

if [ ! -f "$PDK_SRC" ]; then
  echo "Error: $PDK_SRC not found (wrong working directory?)" >&2
  exit 1
fi

# Determine account name (from signer.conf or prompt)
ACCOUNT=""
if [ -f "$CONFIG_FILE" ]; then
  ACCOUNT="$(grep -E '^github_username=' "$CONFIG_FILE" 2>/dev/null | cut -d= -f2 | tr -d ' ' || true)"
fi
if [ -z "$ACCOUNT" ]; then
  read -rp "GitHub username (for keychain account): " ACCOUNT
fi
[ -z "$ACCOUNT" ] && { echo "Error: no account given" >&2; exit 1; }

# ── Ask the user for the passphrase (once, used in both encryption + keychain)
echo "=== Performance Dudes — Harden Signing ==="
echo ""

if grep -q "ENCRYPTED" "$KEY" 2>/dev/null; then
  KEY_ALREADY_ENCRYPTED=1
  echo "Key already encrypted. We need the existing passphrase to store it in Keychain."
  echo "Enter the passphrase you set previously:"
  read -rs -p "Passphrase: " PW
  echo ""

  # Verify it by attempting a decrypt to /dev/null via fd
  if ! printf '%s\n' "$PW" | openssl pkey -passin stdin -in "$KEY" -out /dev/null 2>/dev/null; then
    echo "Error: wrong passphrase or decryption failed" >&2
    PW=""
    exit 1
  fi
  echo "✓ Passphrase verified."
else
  KEY_ALREADY_ENCRYPTED=0
  echo "Key at $KEY is currently NOT encrypted."
  echo ""
  echo "⚠️  IMPORTANT"
  echo "   Save the passphrase in your password manager FIRST."
  echo "   If you lose it, the key is UNRECOVERABLE."
  echo "   No unencrypted backup will be kept."
  echo ""
  read -rp "Continue? [y/N] " answer
  [[ ! "$answer" =~ ^[Yy]$ ]] && { echo "Aborted."; exit 0; }

  # Suggest a strong random passphrase (32 bytes, base64-safe ~43 chars)
  SUGGESTED="$(LC_ALL=C openssl rand -base64 32 | tr -d '\n' | tr '/+' '_-' | cut -c1-43)"
  echo ""
  echo "Suggested strong passphrase (43 chars, ~256 bits of entropy):"
  echo ""
  echo "    $SUGGESTED"
  echo ""
  echo "Save it in your password manager now, then:"
  echo "  [ENTER]  use this suggested passphrase"
  echo "  [type]   type your own instead"
  echo ""
  read -rs -p "Your passphrase (or ENTER for suggested): " PW
  echo ""

  if [ -z "$PW" ]; then
    PW="$SUGGESTED"
    echo "Using suggested passphrase."
    echo "⚠️  Make sure you saved it in your password manager above!"
  else
    read -rs -p "Confirm:                             " PW2
    echo ""
    if [ "$PW" != "$PW2" ]; then
      echo "Error: passphrases don't match" >&2
      PW=""
      PW2=""
      SUGGESTED=""
      exit 1
    fi
    PW2=""
  fi

  SUGGESTED=""
fi

# ── Step 1: Encrypt the key (if not already) ─────────────────────────────────
if [ "$KEY_ALREADY_ENCRYPTED" -eq 0 ]; then
  echo ""
  echo "[1/3] Encrypting $KEY..."
  TMPDIR="$(mktemp -d)"
  trap 'find "$TMPDIR" -type f -exec rm -f {} + 2>/dev/null; rm -rf "$TMPDIR"' EXIT

  printf '%s\n' "$PW" | openssl pkcs8 -topk8 \
    -v2 aes-256-cbc -v2prf hmacWithSHA512 -iter 600000 \
    -passout stdin \
    -in "$KEY" -out "${TMPDIR}/encrypted.pem"

  # Atomically replace (no unencrypted backup)
  mv "${TMPDIR}/encrypted.pem" "$KEY"
  chmod 600 "$KEY"
  echo "  ✓ encrypted (AES-256-CBC / HMAC-SHA512 / 600k PBKDF2 iterations)"
else
  echo ""
  echo "[1/3] Key already encrypted — skipping."
fi

# ── Step 2: Compile and install pd-keychain ──────────────────────────────────
echo ""
echo "[2/3] Installing pd-keychain helper..."

NEEDS_BUILD=1
if [ -x "$PDK_DEST" ] && [ "$PDK_DEST" -nt "$PDK_SRC" ]; then
  NEEDS_BUILD=0
  echo "  pd-keychain already up to date at $PDK_DEST"
fi

if [ "$NEEDS_BUILD" -eq 1 ]; then
  if ! command -v swiftc >/dev/null 2>&1; then
    echo "Error: swiftc not found." >&2
    echo "Install Xcode Command Line Tools: xcode-select --install" >&2
    PW=""
    exit 1
  fi
  mkdir -p "$(dirname "$PDK_DEST")"
  swiftc -O -o "$PDK_DEST" "$PDK_SRC"
  chmod 755 "$PDK_DEST"
  echo "  ✓ compiled and installed: $PDK_DEST"
fi

# Warn if ~/.local/bin is not on PATH
case ":$PATH:" in
  *":${HOME}/.local/bin:"*) ;;
  *)
    echo "  ⚠️  ${HOME}/.local/bin is not on your PATH."
    echo "     Add to ~/.zshrc:  export PATH=\"\$HOME/.local/bin:\$PATH\""
    ;;
esac

# ── Step 3: Store passphrase in Keychain (Touch ID ACL) ──────────────────────
echo ""
echo "[3/3] Storing passphrase in macOS Keychain for account '$ACCOUNT'..."
printf '%s\n' "$PW" | "$PDK_DEST" store "$ACCOUNT"
echo "  ✓ stored (Touch ID / Apple Watch / login password required for reads)"

# Update signer.conf with keychain_account
mkdir -p "$CONFIG_DIR"
if [ -f "$CONFIG_FILE" ] && grep -q '^keychain_account=' "$CONFIG_FILE"; then
  awk -v a="$ACCOUNT" '
    /^keychain_account=/ { print "keychain_account=" a; next }
    { print }
  ' "$CONFIG_FILE" > "${CONFIG_FILE}.tmp" && mv "${CONFIG_FILE}.tmp" "$CONFIG_FILE"
else
  echo "keychain_account=$ACCOUNT" >> "$CONFIG_FILE"
fi
chmod 600 "$CONFIG_FILE"
echo "  ✓ config updated: keychain_account=$ACCOUNT"

# Clear passphrase from memory (best effort)
PW=""

echo ""
echo "=== Done ==="
echo ""
echo "Test — Touch ID prompt should appear:"
echo "  uv run scripts/sign.py some.pdf"
echo ""
echo "Cross-device note:"
echo "  This keychain item is bound to THIS Mac (required for Touch ID)."
echo "  On a new Mac, run this script again — you'll need the passphrase"
echo "  from your password manager."
