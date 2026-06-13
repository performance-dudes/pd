---
name: git-worktrees
description: How to set up and operate git worktree layouts — single-repo and nested (a repo whose worktrees each contain a checkout of another repo). Covers the bare-repo + per-branch-worktree pattern, the rule that all `.bare-*` folders are hoisted to one place at the outermost level, per-repo choice of classic-clone vs worktree, naming conventions, and add/remove/cleanup commands. Use when setting up a fresh workspace, adding or removing a worktree, onboarding a nested repo, or when the user mentions worktrees, `.bare`, "checkout vs worktree", or asks where a repo's bare lives.
---

# Git Worktrees

A worktree layout replaces the usual single `<repo>/.git` checkout with a **bare
repo** plus **one checked-out worktree per branch / PR**. Branches stop fighting
over one working tree — `main` stays clean for reads, each PR gets its own
directory with isolated build artefacts, and no `git stash` ping-pong.

This is opt-in **per repo**. Some repos want it (frequent parallel PRs); most
don't (infrequent changes, or tooling that chokes on bare repos).

## Two layouts, chosen per repo

| Layout | When | Shape |
|---|---|---|
| **classic** | Default. Infrequent PRs, small surface, or worktree-hostile tooling. | `<repo>/.git`, single checkout |
| **worktree** | Parallel PRs are common; artefact isolation helps. | `<repo>/.bare` + one worktree per branch |

The choice is recorded, not guessed. Each repo declares its recommendation under
a `## Setup default` heading in its own `CLAUDE.md`. That default is a
**recommendation, not a constraint** — a team member may always override it for
their local copy. See "Recording the choice" below.

## Single-repo worktree layout

```
<repo>/
  .bare/                 # the bare repository (no working tree)
  .git                   # file, one line: "gitdir: ./.bare"
  main/                  # worktree of main — always clean, quick reads
  pr42-feature/          # one worktree per open PR
  pr57-bugfix/
```

Set up a fresh worktree clone:

```bash
mkdir <repo> && cd <repo>
git clone --bare git@github.com:<org>/<repo>.git .bare
echo "gitdir: ./.bare" > .git
git -C .bare config remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'
git -C .bare fetch origin
git worktree add main main
cd ..
```

Add a worktree for new work (run from the bare):

```bash
cd <repo>/.bare
git worktree add ../pr<n>-<slug> -b <branch-name> origin/main
```

Worktree naming: `pr<n>-<slug>` (PR-driven) or `feat-<slug>` / `docs-<slug>`
(branch-driven). Be consistent within a repo — match what's already there.

## Nested worktree layout

A **nested** setup is an outer repo whose worktrees each contain a checkout of
a second, independent repo (e.g. an outer workspace that holds an inner app repo
inside it). Both repos use worktrees.

**The rule: all `.bare-*` folders live in ONE place — the outermost level.**
The nested repo's worktrees physically sit inside the outer worktrees, but its
bare is *hoisted* up next to the outer repo's bare. There is exactly one bare
per repo, shared by all of that repo's worktrees wherever they sit.

**Two levels, on purpose.** The nested repo splits across depths:

- its **worktrees go deep** — one container folder (`app/`) inside *every* outer
  worktree, with the actual checkout one level deeper
  (`main/app/develop`, `feat-refactor/app/feat-refactor`). The container is a
  plain directory: never a worktree, never holds a `.bare`.
- its **bare stays shallow** — hoisted *out* to the outermost root
  (`workspace/.bare-app`), exactly one, shared by all those scattered worktrees.

So a fresh `git clone --bare` of the nested repo does **not** land inside the
outer worktree where you'll use it — you clone it at the root and point the
worktrees back at it. Worktrees nested; bare hoisted.

```
workspace/                            # outermost level — ALL bares live here
  .bare-workspace/                    # bare for the OUTER repo
  .bare-app/                          # bare for the NESTED repo (hoisted up here)
  .git                                # "gitdir: ./.bare-workspace"
  main/                               # outer worktree
    app/                              # nested repo's worktree container
      develop/                        #   nested worktree  ─┐
      feat-login/                     #   nested worktree   ├─ all share
  feat-refactor/                      # another outer worktree
    app/
      feat-refactor/                  #   nested worktree  ─┘  .bare-app
```

Every nested worktree, regardless of which outer worktree it lives under,
resolves its common git dir to the single hoisted bare:

```bash
git -C workspace/main/app/develop                  rev-parse --git-common-dir
# → workspace/.bare-app
git -C workspace/feat-refactor/app/feat-refactor   rev-parse --git-common-dir
# → workspace/.bare-app   (same bare)
```

Naming when bares are hoisted and there is more than one: `.bare-<repo>` (e.g.
`.bare-workspace`, `.bare-app`). A lone bare may stay `.bare`.

### Set up the nested repo's bare (hoisted)

From the outermost level (`workspace/`):

```bash
cd workspace
git clone --bare git@github.com:<org>/app.git .bare-app
git -C .bare-app config remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'
git -C .bare-app fetch origin
```

Then add a nested worktree *inside* whichever outer worktree needs it, pointing
back at the hoisted bare:

```bash
git -C workspace/.bare-app worktree add \
  ../main/app/develop develop
```

The nested checkout's `.git` file points at the hoisted bare's `worktrees/`
entry — never at a per-outer-worktree copy. There is never a `.bare-app`
inside `main/` or any other outer worktree.

## Operating commands

Drive worktree management through the bare with `--git-dir`, so it works from
the outermost level regardless of which worktree you're in:

```bash
# list every worktree of a repo
git --git-dir=.bare-workspace worktree list

# add (outer repo)
git --git-dir=.bare-workspace worktree add main main
# add (nested repo, into an outer worktree)
git --git-dir=.bare-app worktree add main/app/develop develop

# remove a worktree after its PR/MR is merged
git --git-dir=.bare-workspace worktree remove <folder>
git --git-dir=.bare-workspace branch -D <branch>
git --git-dir=.bare-workspace fetch --prune origin   # tidy remote-tracking refs
```

Cleanup after merge is the branch owner's duty (or the next agent's): remove the
worktree folder, delete the local branch, prune. The nested repo gets the same
treatment via its own `.bare-<nested>`.

## Recording the choice (every project)

For each workspace, the layout decision per repo must be **kept**, not
re-derived each time:

1. **Read the repo's own `CLAUDE.md` → `## Setup default`** for its declared
   recommendation (`classic` or `worktree`, and why). No central allowlist —
   each repo owns its declaration.
2. **No `## Setup default`?** Fall back to **classic**. Filling it in is a small
   docs PR in that repo, not a precondition for cloning.
3. **Ask the person once** whether to follow the default or override. Per-person
   preference wins — the default just avoids per-repo back-and-forth on a fresh
   setup.
4. **Be idempotent.** Detect an existing layout before acting: a `.bare`/`.bare-*`
   + `.git` file means worktree; a `.git` directory means classic. If it's
   already set up the chosen way, skip.
5. Once chosen, respect whatever layout the local copy actually has — don't
   "fix" a classic clone into a worktree or vice versa without being asked.

## Gotchas

- The top-level `.git` is a **file** (`gitdir: ./.bare`), not a directory.
- A hoisted bare must use the `+refs/heads/*:refs/remotes/origin/*` fetch
  refspec, or `git fetch` won't populate remote-tracking branches in a bare
  clone.
- Never put a nested repo's bare inside an outer worktree — it would be
  duplicated per outer worktree and the "one bare per repo" invariant breaks.
- The container folder (`app/`) is a plain directory. If it carries its own
  `.git` file (e.g. `gitdir: ../.bare-app`, left over from an early nested clone
  before hoisting), that's stale cruft — it resolves to a non-existent
  `<outer-worktree>/.bare-app`. Delete it; the real worktrees one level down
  point at the hoisted bare via their own `.git` files. Confirm with
  `git --git-dir=.bare-app worktree list` — only the deep checkouts should appear.
- Worktree directories are gitignored siblings inside the outer repo; never
  commit a worktree folder or a `.bare-*`.
