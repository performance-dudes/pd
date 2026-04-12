#!/usr/bin/env bash
#
# Compile the pd-keychain Swift helper and install it to ~/.local/bin.
#
# Requires: Xcode Command Line Tools (xcode-select --install)
#
# What the helper does:
#   Stores/retrieves your signing key passphrase in the macOS Data Protection
#   Keychain with a user-presence access control (Touch ID / watch / password).
#   Each access triggers a biometric prompt.
#
# Usage:
#   ./scripts/install-keychain-helper.sh

set -euo pipefail

if [ "$(uname -s)" != "Darwin" ]; then
  echo "Error: this helper is macOS-only" >&2
  exit 1
fi

if ! command -v swiftc >/dev/null 2>&1; then
  echo "Error: swiftc not found." >&2
  echo "Install Xcode Command Line Tools: xcode-select --install" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE="${REPO_ROOT}/tools/pd-keychain.swift"
DEST="${HOME}/.local/bin/pd-keychain"

if [ ! -f "$SOURCE" ]; then
  echo "Error: source not found: $SOURCE" >&2
  exit 1
fi

mkdir -p "$(dirname "$DEST")"

echo "Building pd-keychain..."
swiftc -O -o "$DEST" "$SOURCE"
chmod 755 "$DEST"

echo "✓ Installed: $DEST"
echo ""

# Warn if ~/.local/bin is not on PATH
case ":$PATH:" in
  *":${HOME}/.local/bin:"*)
    ;;
  *)
    echo "⚠️  ${HOME}/.local/bin is not on your PATH."
    echo "   Add to ~/.zshrc:  export PATH=\"\$HOME/.local/bin:\$PATH\""
    ;;
esac

echo ""
echo "Next:"
echo "  1. Store your signing passphrase (prompts once, then Touch ID for future reads):"
echo "       ./scripts/store-passphrase.sh"
echo ""
echo "  2. Sign a PDF — sign.py will ask Touch ID for the passphrase:"
echo "       uv run scripts/sign.py document.pdf"
