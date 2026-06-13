# Plugins & Skills

How Claude Code capability is packaged in a workspace, and the recipe for adding a skill.

## Plugins are declared in the workspace

The workspace `.claude/settings.json` declares which plugins are enabled and where their
marketplaces live. Both are installed from **local clones** inside the workspace, so a fresh
checkout gets them automatically once the sub-repos are cloned:

```json
{
  "enabledPlugins": {
    "pd@pd": true,
    "skills-private@skills-private": true
  },
  "extraKnownMarketplaces": {
    "pd":             { "source": { "source": "directory", "path": "./pd" } },
    "skills-private": { "source": { "source": "directory", "path": "./skills-private" } }
  }
}
```

The marketplace `path` points at the local sibling clone (`./pd`, `./skills-private`), not at
a GitHub URL. That is why the setup flow runs `claude plugin marketplace add ./<plugin>`
followed by `claude plugin install <plugin>` and then `/reload-plugins`.

## Plugin anatomy

```
<plugin>/
├── .claude-plugin/
│   ├── plugin.json         ← name, description, version, author
│   └── marketplace.json    ← marketplace entry (name, source, version)
└── skills/
    └── <skill-name>/
        ├── SKILL.md        ← the skill itself
        └── references/     ← optional supporting docs
```

Note: a plugin may itself sit in a worktree-layout repo. For example, the PD `pd` plugin
lives at `pd/main/` (its `main` worktree), so its plugin files are at
`pd/main/.claude-plugin/…` and `pd/main/skills/…`.

## Skill conventions

- One skill = one folder: `skills/<name>/SKILL.md`, **exactly one level deep** (never nested
  in further subdirectories).
- Folder names are **kebab-case** (`project-structure`, `git-worktrees`, `agent-sync-usage`).
- Frontmatter is a `---` block with two keys:
  - `name` — the skill identifier (matches the folder).
  - `description` — one sentence that says *what it is* and *when to use it*. Pack it with
    trigger phrases and cross-references to sibling skills; this text is how the skill gets
    selected, so make it earn its selection.
- Keep `SKILL.md` scannable. Push long how-to detail into `skills/<name>/references/*.md`
  and link to them from the body.

## Adding a skill

1. Create `skills/<name>/SKILL.md` with `name` + `description` frontmatter.
2. Keep it exactly one level deep (`skills/<name>/SKILL.md`, not nested deeper).
3. Put reference docs in `skills/<name>/references/`.
4. **Bump `version` in `.claude-plugin/plugin.json`** so the plugin cache refreshes. Keep the
   `marketplace.json` version aligned.
5. Commit, push, then `claude plugin install <plugin>` and `/reload-plugins` to pick it up.
