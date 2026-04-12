#!/usr/bin/env bash
#
# Store your signing key passphrase in the macOS Keychain with Touch ID
# access control.
#
# Run this YOURSELF — never let Claude (or any other agent) run it.
# The passphrase you type stays in your terminal session only, then goes
# to pd-keychain which places it in the Data Protection Keychain.
#
# Usage:
#   ./scripts/store-passphrase.sh
#
# After running: sign.py will prompt Touch ID instead of asking for the
# passphrase. Your existing encrypted key at ~/.config/pd/private-key.pem
# is not touched.

set -euo pipefail

CONFIG_DIR="${HOME}/.config/pd"
CONFIG_FILE="${CONFIG_DIR}/signer.conf"

# Find pd-keychain binary
if command -v pd-keychain >/dev/null 2>&1; then
  PDK=pd-keychain
elif [ -x "${HOME}/.local/bin/pd-keychain" ]; then
  PDK="${HOME}/.local/bin/pd-keychain"
else
  echo "Error: pd-keychain not installed."
  echo "Run: ./scripts/install-keychain-helper.sh"
  exit 1
fi

# Determine account name from signer.conf (github_username) or prompt
ACCOUNT=""
if [ -f "$CONFIG_FILE" ]; then
  ACCOUNT=$(grep -E '^github_username=' "$CONFIG_FILE" | cut -d= -f2 | tr -d ' ')
fi

if [ -z "$ACCOUNT" ]; then
  read -rp "GitHub username: " ACCOUNT
fi

if [ -z "$ACCOUNT" ]; then
  echo "Error: no account given" >&2
  exit 1
fi

echo "Storing passphrase for account: $ACCOUNT"
echo ""
echo "Enter your signing key passphrase (what you set via protect-key.sh):"
read -rs -p "Passphrase: " PW
echo ""

if [ -z "$PW" ]; then
  echo "Error: empty passphrase" >&2
  exit 1
fi

# Pipe into pd-keychain store — it reads one line from stdin
printf '%s\n' "$PW" | "$PDK" store "$ACCOUNT"

# Clear from memory (best effort in bash)
PW=""

# Update signer.conf to enable keychain integration
mkdir -p "$CONFIG_DIR"
if [ -f "$CONFIG_FILE" ] && grep -q '^keychain_account=' "$CONFIG_FILE"; then
  # Update existing
  awk -v a="$ACCOUNT" '
    /^keychain_account=/ { print "keychain_account=" a; next }
    { print }
  ' "$CONFIG_FILE" > "${CONFIG_FILE}.tmp" && mv "${CONFIG_FILE}.tmp" "$CONFIG_FILE"
else
  echo "keychain_account=$ACCOUNT" >> "$CONFIG_FILE"
fi
chmod 600 "$CONFIG_FILE"

echo ""
echo "✓ Passphrase stored in Keychain under account '$ACCOUNT'."
echo "✓ Config updated: keychain_account=$ACCOUNT"
echo ""
echo "Test (Touch ID prompt should appear):"
echo "  pd-keychain get $ACCOUNT > /dev/null && echo OK"
