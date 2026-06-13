---
name: project-structure
description: How a Performance-Dudes-style workspace is structured — a workspace base repo that orchestrates independent sub-repos, role-based onboarding, classic-vs-worktree layout, the plugin/skill system, communication channels, the pre-commit secret gate, and how a new project is added. Use when someone asks what the workspace repo is for, how the repos fit together, how to set up a machine, where skills/plugins live, or how to spin up a new project. Trigger phrases: "workspace repo", "project structure", "how does the setup work", "what clones where", "add a new project/repo/skill". For the bare/worktree mechanics themselves, defer to the git-worktrees skill.
---

# Project Structure

How a workspace is laid out and why. This describes a **pattern** — a *workspace
base repo* that orchestrates a set of otherwise-independent sub-repos — using
**Performance Dudes** as the running concrete example. The same shape works for any
team that wants one clone point, role-based onboarding, and shared Claude Code config
on top of repos that keep their own lifecycle.

This is explanatory. For the deep how-to detail, follow the `references/` files linked
at the end. For the bare-repo / worktree mechanics, defer to the **`pd:git-worktrees`**
skill — this skill does not restate them.

## The two-layer model

```
workspace-base-repo/          ← you clone THIS, and only this, to start
├── CLAUDE.md                 ← setup instructions Claude follows
├── .claude/settings.json     ← declares plugins + local marketplaces
├── lefthook.yml              ← shared pre-commit secret gate
├── sub-repo-a/               ← cloned sibling (gitignored here)
├── sub-repo-b/               ← cloned sibling (gitignored here)
└── …
```

Two layers:

1. **The workspace base repo** — a thin orchestrator. It is a *single clone point* and a
   *config hub*, not a monorepo. It holds setup instructions, shared Claude Code config,
   and the secret-gate config. It does **not** contain the sub-repos' code.
2. **The sub-repos** — independent repositories cloned as **siblings inside** the workspace
   directory. Each has its own visibility (public/private), its own `CLAUDE.md`, its own
   release cadence and CODEOWNERS. They are **gitignored** in the workspace repo: they live
   there for convenience but are managed separately.

The key idea: cloning one repo and starting Claude Code is enough to bootstrap everything
else. The workspace repo knows *what* to clone and *how*, per the user's role.

## Why a workspace repo

- **Single entry point.** New collaborators clone one repo and run `claude`; the setup is
  guided from there. No "here's a list of 7 repos to clone in the right order" wiki page.
- **Role-based onboarding.** The base `CLAUDE.md` maps each role to the repos it should get.
  People only clone what they have access to and need.
- **Config hub.** Shared Claude Code config lives once in the workspace: enabled plugins and
  their local marketplace paths (`.claude/settings.json`), and the pre-commit secret gate
  (`lefthook.yml`). Sub-repos inherit the gate and can add their own.
- **Hands off sub-repo internals.** The workspace orchestrates *setup*; it never modifies a
  sub-repo's contents or structure. Each sub-repo owns its own rules.

## The repo landscape & roles

A workspace typically mixes a few kinds of sub-repo:

| Kind | Example (PD) | Visibility | Role |
|---|---|---|---|
| Orchestrator | `performance-dudes` | public | The workspace base repo itself |
| Public infrastructure | `trust` | public | Auditable PKI / shared infra |
| Plugin (skills) | `pd`, `skills-private`, `culture` | public / private | Ships Claude Code skills |
| Private strategy | `orga`, `trust-keys` | private | Decisions, secrets audit trail |
| Assets | `brand` | private | Ready-to-use assets |

**Roles** decide who clones what. In PD:

| Role | Clones |
|---|---|
| Founder | `trust`, `trust-keys`, `orga`, `pd`, `skills-private`, `culture`, `brand` |
| Partner | `trust`, `trust-keys`, `pd`, `skills-private`, `brand` |
| Member | `trust`, `pd`, `brand` |
| Just exploring | `trust`, `pd` |

Sub-repos clone **into** the workspace directory — `./trust/`, `./pd/`, … — as gitignored
siblings, not into the user's home directory. (Authority for the location convention in PD:
`orga/decisions/2026-05-07-companion-workspace-location.md`.)

## On-disk layout

Each sub-repo is laid out as either a **classic clone** (`<repo>/.git`, single checkout) or a
**worktree layout** (`<repo>/.bare` + one worktree per branch/PR). The choice is made **per
repo** and recorded in that repo's own `CLAUDE.md` under a `## Setup default` heading — there
is no central allowlist. A team member may always override the default for their local copy.

→ For the full mechanics — bare repos, the hoisted-`.bare-*` rule for nested layouts, naming,
and add/remove/cleanup commands — use the **`pd:git-worktrees`** skill. This skill only tells
you *that* the choice exists and *where* it is recorded.

## Go deeper

- **`references/setup.md`** — prerequisites, the guided clone-per-role flow, plugin
  registration, and the merge policy.
- **`references/plugins-and-skills.md`** — how plugins and skills are organized, local
  marketplaces, and the recipe for adding a skill.
- **`references/channels-and-security.md`** — the `pd-sync` / `agent-sync` communication
  channels, the pre-commit secret gate, and shared-doc conventions.
- **`references/new-project.md`** — what it takes to add a brand-new project/sub-repo to a
  workspace (explanatory; no template).
