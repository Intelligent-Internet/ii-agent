# Contributing to II-Agent

Welcome — and thank you for helping build **II-Agent**, an open-source, community-driven framework for autonomous agents.  
Whether you are filing an issue, improving documentation, adding tests, or implementing a new feature, your participation helps everyone.

---

## 🌍 Open-Source Spirit

II-Agent exists **because** of open collaboration.  
By making the full source code, tests, benchmarks, and docs public we enable:

* **Transparency** – anyone can inspect how the agent plans, calls tools, and manages context.  
* **Rapid innovation** – ideas are shared, discussed, and merged at internet speed.  
* **Collective ownership** – no contribution is too small; typos, examples, bug fixes, and ambitious features all move the project forward.  
* **Inclusive learning** – contributors of every background and skill level grow together through code reviews and discussion.

We invite **students, researchers, hobbyists, and professionals** alike to join us. Your perspective can turn II-Agent into an even more amazing product.

---

## Table of Contents

1. Getting Started  
2. Fork & Clone Workflow  
3. Branching Strategy  
4. Coding Style & Tooling  
5. Running Tests  
6. Issue Reporting  
7. Pull-Request Process  
8. Review Expectations  
9. Communication Channels  
10. Support

---

## 1. Getting Started

```bash
# 1. Fork the repo on GitHub
# 2. Clone your fork
git clone git@github.com:<your-username>/ii-agent.git
cd ii-agent

# 3. Add upstream remote
git remote add upstream https://github.com/Intelligent-Internet/ii-agent.git

# 4. Setup virtual env
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate

# 5. Install dependencies + dev tools
pip install -e .[dev]
pre-commit install                  # format & lint hooks
```

Prefer containers? `docker compose up --build` launches backend, database, and frontend automatically.

---

## 2. Fork & Clone Workflow

Keep your fork in sync:

```bash
git checkout main
git fetch upstream
git rebase upstream/main
git push origin main
```

Create a **feature branch** for every change:

```bash
git checkout -b feat/<short-description>
```

---

## 3. Branching Strategy

| Prefix | Purpose                      | Example                      |
|--------|-----------------------------|------------------------------|
| `feat/`| New feature                 | `feat/browser-automation`    |
| `fix/` | Bug fix                     | `fix/context-truncation`     |
| `docs/`| Documentation only          | `docs/architecture`          |
| `refactor/`| Internal refactor       | `refactor/token-counter`     |
| `test/`| Add or improve tests        | `test/context-manager`       |
| `chore/`| Build, CI, deps, cleanup   | `chore/upgrade-playwright`   |

Small, focused branches merge fastest.

---

## 4. Coding Style & Tooling

| Concern           | Tool / Rule                           |
|-------------------|---------------------------------------|
| Formatting        | **Black** (auto-format)               |
| Import ordering   | **isort**                             |
| Linting           | **ruff**                              |
| Type checking     | **mypy** (optional but encouraged)    |
| Commit messages   | **Conventional Commits**              |

Run all hooks locally:

```bash
pre-commit run --all-files
```

CI executes the same hooks; failing checks block merge.

---

## 5. Running Tests

```bash
pytest -q                 # run all tests
pytest tests/llm          # subset
```

Please add or update tests for every new feature or bug fix.

---

## 6. Issue Reporting

1. **Search first** to avoid duplicates.  
2. Use GitHub’s issue templates: *Bug*, *Feature*, *Docs*.  
3. Provide clear steps, logs, and environment details.

---

## 7. Pull-Request Process

1. Rebase your branch on `upstream/main`.  
2. Push to **your** fork and open a PR against **Intelligent-Internet/ii-agent:main**.  
3. Fill in the PR template (what, why, checklist).  
4. Draft PRs are welcome for early feedback.  
5. Ensure CI is green; respond to reviewer comments promptly.

---

## 8. Review Expectations

* At least **one maintainer approval** required.  
* Reviewers may request changes for clarity, style, tests, or docs.  
* Discussions happen in the PR; feel free to ask questions.  
* We squash-merge by default to keep history clean.

---

## 9. Communication Channels

| Channel            | Purpose                             |
|--------------------|-------------------------------------|
| GitHub Issues      | Bugs, feature requests              |
| GitHub Discussions | Questions, design proposals         |
| Discord            | Real-time chat with community       |
| Mailing List       | Release announcements               |
| Security Email     | `security@ii.inc` – vuln disclosure |

---

## 10. Support

See [`docs/usage.md`](docs/usage.md) for installation & troubleshooting, and [`docs/examples.md`](docs/examples.md) for step-by-step demos.  
For general help, open a GitHub Discussion or join Discord.

---

**Thank you** for making II-Agent better. Every commit, comment, and review counts!  
Together we’ll push the boundaries of autonomous agents.
