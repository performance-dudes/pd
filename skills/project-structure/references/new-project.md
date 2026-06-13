# Adding a new project to the workspace

What it *means* to add a brand-new project (sub-repo) to a workspace, and the moving parts you
have to wire up. This is explanatory — there is no template to copy. The goal is to understand
each piece so you can make the right call for the specific project.

## 1. Decide what the project is

The kind of project drives every later decision:

- **Public infrastructure** (like `trust`) — auditable, no plaintext secrets ever, often
  CODEOWNERS-gated.
- **A plugin** (like `pd`, `culture`) — ships Claude Code skills; needs `.claude-plugin/` and a
  marketplace entry (see step 4).
- **Private strategy / assets** (like `orga`, `brand`) — access-restricted; visibility is the
  first thing to get right.
- **An app / client code** — its own build tooling, which may favor or reject a worktree layout.

## 2. Create the repo with its own lifecycle

A sub-repo is **independent**, not a folder of the workspace. Give it:

- Its **own visibility** (public vs private) — chosen deliberately, because it can't be quietly
  changed later without consequences.
- Its **own `CLAUDE.md`** with its rules, and crucially a `## Setup default` heading declaring
  `classic` or `worktree` (and why). Onboarding reads that heading; no `## Setup default` means
  the default is `classic`. See `setup.md` and the `pd:git-worktrees` skill.
- Its **own CODEOWNERS / branch protection** if it warrants review gates (infra and key repos
  usually do).

The workspace never owns this repo's internals — it only learns *how* to clone it.

## 3. Wire it into onboarding

For the guided setup to clone the new repo for the right people, add it to the **workspace
role/clone matrix** (in PD, the table in the base `CLAUDE.md`). Decide which roles get it. A
repo nobody's role lists is a repo nobody clones.

It will clone as a **gitignored sibling** inside the workspace directory (`./<repo>/`). The
workspace's whitelist-style `.gitignore` must not accidentally start tracking it — it stays
managed independently and is never committed into the workspace repo.

## 4. If it ships Claude skills, make it a plugin

A project that provides skills becomes a plugin:

- Add `.claude-plugin/plugin.json` (name, description, version, author) and a
  `marketplace.json` entry.
- Put skills under `skills/<name>/SKILL.md` (one level deep) with optional `references/`. See
  `plugins-and-skills.md` for the full anatomy and the add-a-skill recipe.
- Register its **local marketplace** in the workspace `.claude/settings.json`
  (`extraKnownMarketplaces` → a `directory` source pointing at `./<repo>`) and enable it under
  `enabledPlugins`. That is what makes a fresh workspace pick it up automatically.

## Reasoning notes

- **Independence over coupling.** Each sub-repo keeps its own visibility, release cadence, and
  ownership. The workspace coordinates setup; it does not absorb the repos.
- **One bare per repo** if it uses a worktree layout — and for nested layouts, the bare is
  hoisted to the outermost level. The `pd:git-worktrees` skill is the authority here.
- **Idempotent setup.** Whatever you add must be safe to re-run: detect an existing clone,
  plugin, or hook and skip rather than redo.
- **No secrets in tracked files.** New repos inherit the same rule — real secrets go in
  `~/.config/pd/` (gitignored); see `channels-and-security.md`.
