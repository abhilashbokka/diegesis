# Contributing

## Branching model

Simplified Git Flow. Two long-lived branches, everything else short-lived.

```
main        release-ready. Tagged. Never committed to directly.
 └── develop      integration branch. Default branch; PRs target it.
      ├── feature/<name>    new work
      ├── fix/<name>        bug fixes
      ├── chore/<name>      tooling, dependencies, housekeeping
      ├── docs/<name>       documentation only
      ├── release/<version> stabilise before a release
      └── hotfix/<name>     urgent fix, branches from main
```

### Why there is no `test` branch

A `test` or `staging` branch earns its place when there is an **environment to deploy into** — a staging server that has to hold a specific build while it is exercised. These are libraries and research repositories with no deploy target, so a test branch would add a merge hop and buy nothing.

Testing happens in two places instead, both earlier than a branch would allow:

- **Locally**, before the commit: `uv run pytest`, `uv run ruff check .`
- **On the pull request**, against `develop`, where every branch is covered rather than just the one that reached staging.

`develop` *is* the integration-test branch. Adding another would mean code sits untested for longer, not shorter.

### Workflow

```bash
git checkout develop && git pull
git checkout -b feature/spatial-separation

# work, committing as you go
uv run pytest && uv run ruff check .

git push -u origin feature/spatial-separation
# open a PR into develop
```

Merges use `--no-ff` so the branch structure stays visible in history:

```bash
git checkout develop
git merge --no-ff feature/spatial-separation
git push origin develop
```

Releasing:

```bash
git checkout main
git merge --no-ff develop
git tag -a v0.2.0 -m "v0.2.0"
git push origin main --tags
```

### Rules

- **Never commit directly to `main`.** It moves only by merge from `develop` or a hotfix.
- **Never commit directly to `develop`** once a change is more than trivial — branch, then merge.
- **Never force-push** `main` or `develop`.
- Keep branches short-lived. A branch open for weeks will conflict.
- One concern per branch. A branch that touches the analyser *and* the CLI *and* the docs is three branches.

### Branch protection

`main` is protected: no force pushes, no deletion, changes arrive by pull request. Diegesis is public, so protection is available on the current GitHub plan.

The private research repository cannot be protected — GitHub restricts that to paid plans for private repositories — so there the rules above are convention rather than enforcement.

## Before pushing

```bash
uv run pytest            # must pass
uv run ruff check .      # must be clean
uv run ruff format .
```

## What must never be committed

- **Audio, video, model weights, corpora.** All gitignored. They belong in `data/`, which is not tracked.
- **Research materials.** `docs/research/` is a separate private repository, gitignored by the parent. Never `git add -f` anything from it. This repository is **public** — anything committed here is permanent.
- **Film and television audio.** Never redistributable. Publish pointers, timestamps and extracted features instead.

## Commit messages

Imperative mood, explaining *why* rather than restating the diff. If a change corrects an earlier mistake, say what the mistake caused — that context is what makes a log worth reading a year later.

## Contribution policy

**External contributions are not currently accepted.** Diegesis is licensed under PolyForm Noncommercial, and the licence is provisional through alpha — it may move to a permissive open-source licence, stay noncommercial, or close. Only code whose copyright is wholly owned keeps all three options open, and accepting a contribution without a contributor licence agreement would foreclose them.

This will be revisited once the licence is settled. Until then, please open an issue rather than a pull request.
