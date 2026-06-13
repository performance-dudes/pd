# Channels & Security

Two cross-cutting concerns the workspace owns: how Claude sessions talk to each other, and
how the workspace keeps secrets out of commits.

## Communication channels

A workspace can bridge separate Claude Code sessions (and humans) over a shared channel. PD
runs two, registered in `.mcp.json` and running **in parallel**:

| Channel | Status | Shape |
|---|---|---|
| `pd-sync` | **Stable, in operation.** | MCP channel server (`channels/pd-sync/`). Bridges two Claude Code sessions via a shared Signal group, fronted by Cloudflare Access with GitHub OAuth. |
| `agent-sync` | **Successor, in development; runs alongside.** | Three-tier — remote server + local relay + thin MCP. Lives in its own repo (`performance-dudes/agent-sync`). |

- **One-time machine setup** (not a skill) is documented in each channel's
  `channels/<name>/README.md`.
- **Runtime usage rules** live as skills in the `skills-private` plugin:
  `pd-sync-usage` and `agent-sync-usage`.
- `agent-sync` only activates when its local config exists (`~/.config/pd/agent-sync.json`);
  otherwise it stays **idle**, so it never disturbs `pd-sync`. It replaces `pd-sync` only once
  fully verified.

## Pre-commit secret gate

The workspace ships a `lefthook.yml` pre-commit gate that runs on every commit against the
base repo. (Sub-repos may have their own gates; this is the workspace-level protection.) Two
checks run in parallel:

1. **`gitleaks protect --staged`** — 140+ vendor secret rules against the staged diff.
2. **Custom PD patterns** — supplements gitleaks with PD-specific markers in the staged diff:
   phone numbers in docs, `hcloud` API tokens, Cloudflare Access secrets, and Signal-CLI
   account examples.

**One-time setup per machine:**

```bash
brew install lefthook gitleaks
lefthook install     # registers the native git hook
```

**Bypass** — only for a documented false positive (rare; prefer anonymizing the value):

```bash
LEFTHOOK=0 git commit -m "..."
# or
git commit --no-verify -m "..."
```

When the custom gate fires, the fix is almost always to **anonymize, not bypass**: replace a
phone number with a placeholder like `+49xxxxxxxxxx`, move a token into `~/.config/pd/*`
(gitignored), or strip a real Signal account out of an example.

**Where real secrets live:** in `~/.config/pd/` (gitignored), never in tracked files.

## Shared-doc conventions

- **German umlauts** in tracked files: real `ä ö ü Ä Ö Ü ß`, not ASCII substitutes
  (`ae oe ue ss`). English technical terms and proper names stay unchanged.
- **Workspace-root-relative paths** in shared docs. Refer to `<workspace>/<account>/`,
  `../<sibling>/` between sub-repos — never `~/work/` or other home-directory paths that are
  local to one person.
- **Conventional commits**: `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, `style:`. Header
  says *what* changed; body says *why* (context the diff can't show).
