#!/usr/bin/env bash
#
# Consolidated setup for secure local signing.
#
# Run this YOURSELF after scripts/setup.py has generated the key.
#
# Modes (auto-detected):
#   - Unencrypted key → encrypts it + stores passphrase in Keychain
#   - Encrypted key + no Keychain entry → stores passphrase in Keychain
#   - Encrypted key + Keychain entry already → interactive menu
#     (rotate passphrase / re-store in Keychain / quit)
#
# After setup, sign.py prompts Touch ID instead of asking for the passphrase.
#
# Requires: Xcode Command Line Tools (xcode-select --install)
#
# Portability: Keychain items are device-bound (Touch ID ACL prevents iCloud
# sync by Apple's design). For cross-device use, save the passphrase in your
# password manager (Bitwarden/Vaultwarden) — re-run this on each Mac.

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

CLIPBOARD_CLEAR_SECONDS=60

# ── Sanity checks ────────────────────────────────────────────────────────────
[ "$(uname -s)" = "Darwin" ] || { echo "Error: macOS-only (Touch ID + Keychain)" >&2; exit 1; }
[ -f "$KEY" ] || { echo "Error: no signing key at $KEY — run scripts/setup.py first" >&2; exit 1; }
[ -f "$PDK_SRC" ] || { echo "Error: $PDK_SRC not found" >&2; exit 1; }

# Determine account name
ACCOUNT=""
if [ -f "$CONFIG_FILE" ]; then
  ACCOUNT="$(grep -E '^github_username=' "$CONFIG_FILE" 2>/dev/null | cut -d= -f2 | tr -d ' ' || true)"
fi
if [ -z "$ACCOUNT" ]; then
  read -rp "GitHub username (keychain account): " ACCOUNT
fi
[ -z "$ACCOUNT" ] && { echo "Error: no account given" >&2; exit 1; }

# ── Helpers ──────────────────────────────────────────────────────────────────

suggest_passphrase() {
  LC_ALL=C openssl rand -base64 32 | tr -d '\n' | tr '/+' '_-' | cut -c1-43
}

# Copy to clipboard with auto-clear in background.
# Usage: copy_to_clipboard "text"
copy_to_clipboard() {
  local value="$1"
  if ! command -v pbcopy >/dev/null 2>&1; then
    return 1
  fi
  printf '%s' "$value" | pbcopy
  # Auto-clear clipboard after N seconds (background, detached)
  (
    sleep "$CLIPBOARD_CLEAR_SECONDS"
    current="$(pbpaste 2>/dev/null || echo "")"
    if [ "$current" = "$value" ]; then
      printf '' | pbcopy
    fi
  ) >/dev/null 2>&1 &
  disown 2>/dev/null || true
  return 0
}

# Check if key is encrypted
is_encrypted() {
  grep -q "ENCRYPTED" "$KEY" 2>/dev/null
}

# Verify passphrase by trying to decrypt to /dev/null
verify_passphrase() {
  local pw="$1"
  printf '%s\n' "$pw" | openssl pkey -passin stdin -in "$KEY" -out /dev/null 2>/dev/null
}

# Encrypt key in place using passphrase
encrypt_key_inplace() {
  local pw="$1" src="$2"
  local tmpdir
  tmpdir="$(mktemp -d)"
  printf '%s\n' "$pw" | openssl pkcs8 -topk8 \
    -v2 aes-256-cbc -v2prf hmacWithSHA512 -iter 600000 \
    -passout stdin \
    -in "$src" -out "${tmpdir}/encrypted.pem"
  mv "${tmpdir}/encrypted.pem" "$KEY"
  chmod 600 "$KEY"
  # shred the tmpdir
  find "$tmpdir" -type f -exec rm -f {} + 2>/dev/null || true
  rm -rf "$tmpdir"
}

# Decrypt key to a temp file, echo its path
decrypt_key_to_temp() {
  local pw="$1"
  local tmp
  tmp="$(mktemp)"
  if ! printf '%s\n' "$pw" | openssl pkey -passin stdin -in "$KEY" -out "$tmp" 2>/dev/null; then
    rm -f "$tmp"
    return 1
  fi
  echo "$tmp"
}

# Prompt for new passphrase (suggested or custom), set PW
prompt_new_passphrase() {
  local suggested
  suggested="$(suggest_passphrase)"
  echo ""
  echo "Suggested strong passphrase (43 chars, ~256 bits entropy):"
  echo ""
  echo "    $suggested"
  echo ""
  if copy_to_clipboard "$suggested"; then
    echo "✓ Copied to clipboard — paste into your password manager now"
    echo "  (clipboard auto-clears after ${CLIPBOARD_CLEAR_SECONDS}s)"
  fi
  echo ""
  echo "  [ENTER]  use suggested"
  echo "  [type]   enter your own"
  echo ""
  read -rs -p "Your passphrase (or ENTER): " PW
  echo ""

  if [ -z "$PW" ]; then
    PW="$suggested"
    echo "Using suggested passphrase."
  else
    read -rs -p "Confirm:                   " PW2
    echo ""
    if [ "$PW" != "$PW2" ]; then
      PW=""; PW2=""; suggested=""
      echo "Error: passphrases don't match" >&2
      exit 1
    fi
    PW2=""
  fi
  suggested=""
}

# Check if keychain already has an entry for this account
keychain_has_entry() {
  [ -x "$PDK_DEST" ] && "$PDK_DEST" exists "$ACCOUNT" >/dev/null 2>&1
}

# Store passphrase in Keychain
keychain_store() {
  local pw="$1"
  printf '%s\n' "$pw" | "$PDK_DEST" store "$ACCOUNT"
}

update_config() {
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
}

compile_helper() {
  if [ -x "$PDK_DEST" ] && [ "$PDK_DEST" -nt "$PDK_SRC" ]; then
    return 0
  fi
  command -v swiftc >/dev/null 2>&1 || {
    echo "Error: swiftc not found. Install: xcode-select --install" >&2
    exit 1
  }
  mkdir -p "$(dirname "$PDK_DEST")"
  swiftc -O -o "$PDK_DEST" "$PDK_SRC"
  chmod 755 "$PDK_DEST"
  echo "  ✓ compiled and installed: $PDK_DEST"
}

# ── Main flow ────────────────────────────────────────────────────────────────
echo "=== Performance Dudes — Harden Signing ==="
echo ""

PW=""
MODE=""  # encrypt | store-existing | rotate

if is_encrypted; then
  echo "Key at $KEY is already encrypted."

  # Ensure helper is installed before checking keychain
  compile_helper >/dev/null

  if keychain_has_entry; then
    echo "Keychain already has an entry for '$ACCOUNT'."
    echo ""
    echo "What would you like to do?"
    echo "  [r] Rotate passphrase (change it, update key + Keychain)"
    echo "  [s] Re-store current passphrase in Keychain (e.g. after keychain reset)"
    echo "  [q] Quit"
    echo ""
    read -rp "Choice [r/s/q]: " choice
    case "$choice" in
      r|R) MODE="rotate" ;;
      s|S) MODE="store-existing" ;;
      *) echo "Aborted."; exit 0 ;;
    esac
  else
    echo "No keychain entry yet — will store current passphrase."
    MODE="store-existing"
  fi
else
  echo "Key is NOT encrypted — will encrypt it."
  echo ""
  echo "⚠️  IMPORTANT: save the passphrase in your password manager."
  echo "   If lost, the key is UNRECOVERABLE."
  read -rp "Continue? [y/N] " answer
  [[ "$answer" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }
  MODE="encrypt"
fi

# ── Execute per mode ─────────────────────────────────────────────────────────

case "$MODE" in
  encrypt)
    prompt_new_passphrase
    echo ""
    echo "[1/3] Encrypting key..."
    encrypt_key_inplace "$PW" "$KEY"
    echo "  ✓ encrypted (AES-256-CBC / HMAC-SHA512 / 600k PBKDF2)"
    ;;

  store-existing)
    read -rs -p "Enter current passphrase: " PW
    echo ""
    verify_passphrase "$PW" || { PW=""; echo "Error: wrong passphrase" >&2; exit 1; }
    echo "  ✓ passphrase verified"
    echo ""
    echo "[1/3] Key encryption already in place — skipped."
    ;;

  rotate)
    read -rs -p "Enter CURRENT passphrase: " OLD_PW
    echo ""
    verify_passphrase "$OLD_PW" || { OLD_PW=""; echo "Error: wrong passphrase" >&2; exit 1; }
    echo "  ✓ current passphrase verified"

    # Get new passphrase (suggested or custom)
    prompt_new_passphrase
    NEW_PW="$PW"
    PW=""

    # Decrypt with old, re-encrypt with new
    echo ""
    echo "[1/3] Rotating passphrase on key..."
    TMPKEY="$(decrypt_key_to_temp "$OLD_PW")" || { OLD_PW=""; NEW_PW=""; echo "Error: decrypt failed" >&2; exit 1; }
    OLD_PW=""
    trap 'find "$(dirname "$TMPKEY")" -path "$TMPKEY" -exec rm -f {} + 2>/dev/null; rm -f "$TMPKEY"' EXIT

    encrypt_key_inplace "$NEW_PW" "$TMPKEY"
    rm -f "$TMPKEY"
    trap - EXIT
    echo "  ✓ key re-encrypted with new passphrase"
    PW="$NEW_PW"
    NEW_PW=""
    ;;
esac

# ── Step 2: install pd-keychain (if not done above) ─────────────────────────
echo ""
echo "[2/3] Ensuring pd-keychain helper is installed..."
compile_helper
echo "  ✓ $PDK_DEST"

# PATH check
case ":$PATH:" in
  *":${HOME}/.local/bin:"*) ;;
  *)
    echo "  ⚠️  ${HOME}/.local/bin is not on your PATH."
    echo "     Add to ~/.zshrc:  export PATH=\"\$HOME/.local/bin:\$PATH\""
    ;;
esac

# ── Step 3: store / update in keychain ──────────────────────────────────────
echo ""
echo "[3/3] Storing passphrase in Keychain for account '$ACCOUNT'..."
keychain_store "$PW"
echo "  ✓ stored (Touch ID required for reads)"

update_config
echo "  ✓ config: keychain_account=$ACCOUNT"

# Clear
PW=""

echo ""
echo "=== Done ==="
echo ""
echo "Test — Touch ID prompt should appear:"
echo "  uv run scripts/sign.py some.pdf"
echo ""
echo "Cross-device: re-run this script on each Mac (keychain items are"
echo "device-bound for Touch ID security). Passphrase in your password manager."
