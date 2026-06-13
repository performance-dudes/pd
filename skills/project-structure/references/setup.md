# Setup

How a fresh machine goes from "cloned the workspace repo" to "fully operational". The
workspace `CLAUDE.md` drives this; the steps below are the shape of that walkthrough.

## Principles

- **One command at a time.** Explain what you are about to do, run it, confirm it worked,
  then move on. Don't batch a setup into one opaque script.
- **Idempotent.** Detect existing state and skip. A repo already cloned, a plugin already
  installed, a hook already set up — leave it alone.
- **Never handle plaintext secrets.** If a step needs a passphrase (e.g. hardening a signing
  key), the human runs that command themselves. Claude never captures it.
- **Respect role.** Ask who the person is up front, then follow the matching path. Don't try
  to clone repos they have no access to.

## Prerequisites check

Before cloning anything, verify the toolchain is present:

```bash
command -v git && git --version
command -v gh && gh --version
command -v uv && uv --version
command -v openssl && openssl version
command -v lefthook && lefthook version
command -v gitleaks && gitleaks version
gh auth status
```

Install hints for anything missing:

- `git`: `brew install git`
- `gh`: `brew install gh`, then `gh auth login`
- `uv`: `brew install uv` (or `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- `openssl`: usually pre-installed on macOS
- `lefthook` + `gitleaks`: `brew install lefthook gitleaks` (see `channels-and-security.md`)

Never install tools without asking first — especially anything needing `sudo`.

## Clone the sub-repos (per role)

Identify the role first (in PD: Founder / Partner / Member / Just exploring) and the person's
GitHub username. The role determines the clone list (see the SKILL.md role matrix). Then, for
each repo in that list:

1. **Read the repo's own `CLAUDE.md` → `## Setup default`** for its declared layout
   (`classic` or `worktree`, and why). No `## Setup default`? Fall back to **classic**.
2. **Apply the declared default**, but **ask the person once** whether to follow it or
   override. Per-person preference always wins.
3. Clone into the workspace directory as a gitignored sibling.

**Classic clone:**

```bash
git clone git@github.com:<org>/<repo>.git
```

**Worktree layout** — see the **`pd:git-worktrees`** skill for the full bare-repo recipe and
the hoisted-`.bare-*` rule. Do not improvise it here.

If `git clone` fails for a private repo, the person simply doesn't have access — report it
clearly and move on.

## Register the plugins

A workspace declares its plugins in `.claude/settings.json` and installs them from the
**local clones** (not from a remote). After the plugin repos are cloned:

```bash
claude plugin marketplace add ./<plugin>
claude plugin install <plugin>
```

Then `/reload-plugins` in Claude Code to activate. A private plugin repo requires org
membership. Details and the plugin anatomy: `plugins-and-skills.md`.

## Merge policy

**Never merge a PR without explicit user approval.** When work is ready: open the PR with
`gh pr create`, hand the URL back, and stop. Wait for a clear "merge" instruction before
running `gh pr merge`.

The same restraint applies to actions easily confused with "finishing the PR": branch
deletion, force-pushes that rewrite shared history, and release tagging. None happen without
an explicit go-ahead. Merging is the user's call (timing, branch hygiene, stacked-PR
coordination); Claude's job is to land reviewable changes, not to ship them.
