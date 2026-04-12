---
name: setup-signing
description: Set up local signing environment — install pyHanko, generate key pair, create CSR, configure ~/.config/pd/
---

# Setup Signing Environment

Guide the user through setting up their local signing environment. This is a one-time setup.

## Steps

### 1. Install pyHanko

Check if pyHanko is installed:

```bash
python3 -c "import pyhanko" 2>/dev/null && echo "pyHanko installed" || echo "NOT installed"
```

If not installed:

```bash
pip3 install "pyhanko[opentype]" cryptography
```

If pip complains about system packages, use:

```bash
pip3 install --user "pyhanko[opentype]" cryptography
```

### 2. Create config directory

```bash
mkdir -p ~/.config/pd
```

### 3. Generate end-entity key pair

The private key stays on this machine. Never upload it anywhere.

```bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out ~/.config/pd/private-key.pem
chmod 600 ~/.config/pd/private-key.pem
echo "Private key generated at ~/.config/pd/private-key.pem"
```

### 4. Create Certificate Signing Request (CSR)

Ask the user for their:
- Full name (for the certificate CN)
- Email address
- Their GitHub username (used as the issuer slug)

```bash
openssl req -new -key ~/.config/pd/private-key.pem \
  -out ~/.config/pd/signing.csr \
  -subj "/CN=<full-name>/emailAddress=<email>/O=Performance Dudes"
```

### 5. Submit CSR to the trust repo

The CSR contains only the public key + identity. It's safe to commit.

```bash
cd <path-to-trust-repo>
mkdir -p pki/csrs
cp ~/.config/pd/signing.csr pki/csrs/<github-username>.csr
git add pki/csrs/<github-username>.csr
git commit -m "feat: add CSR for <github-username>"
git push
```

### 6. Trigger certificate issuance

```bash
gh workflow run pki-issue.yml --repo performance-dudes/trust \
  -f issuer=<github-username> \
  -f csr_path=pki/csrs/<github-username>.csr
```

The workflow needs environment approval. After it completes, a PR with the signed certificate appears in the trust repo. Merge it.

### 7. Verify the certificate

```bash
cd <path-to-trust-repo>
git pull
cat pki/issuers/<github-username>/issuing-cert.pem pki/root/ca-cert.pem > /tmp/chain.pem
openssl verify -CAfile /tmp/chain.pem pki/certs/<github-username>.pem
```

### 8. Create signer config

```bash
cat > ~/.config/pd/signer.conf << EOF
github_username=<github-username>
trust_repo=<path-to-trust-repo>
EOF
```

### 9. Done

The user now has:
- `~/.config/pd/private-key.pem` — their private signing key (never leaves this machine)
- `~/.config/pd/signing.csr` — their CSR (submitted to trust repo)
- `~/.config/pd/signer.conf` — signing configuration
- A signed certificate in the trust repo at `pki/certs/<github-username>.pem`

They can now use `/pd:sign` to sign documents.
