# bmad-loop-adapter-goose

Community CLI adapter for [bmad-loop](https://github.com/bmad-code-org/bmad-loop)
that drives [Goose](https://github.com/aaif-goose/goose) over the Agent Client
Protocol (ACP) on stdio (`goose acp`).

The adapter registers itself via the `bmad_loop.cli_adapters` entry-point
group, so no manual configuration step is needed — once co-installed,
bmad-loop discovers the Goose profile and adapter automatically.

## Prerequisites

- [Goose](https://github.com/aaif-goose/goose) installed and a provider
  configured (`goose configure`)
- [uv](https://docs.astral.sh/uv/) installed
- [Node.js](https://nodejs.org) 20.12+ (for the BMAD-METHOD installer)

## Install

bmad-loop is not on PyPI — it installs from GitHub. This adapter requires the
CLI adapter entry-point registry, which is currently on a feature branch
pending merge into bmad-loop's `main`. Install both together:

```bash
uv tool install "bmad-loop[tui] @ git+https://github.com/robjgray/bmad-loop.git@feat/cli-adapter-registry-v2" \
  --with "bmad-loop-adapter-goose @ git+https://github.com/robjgray/bmad-loop-adapter-goose.git"
```

Once the registry lands in a bmad-loop release, this simplifies to the
maintainer's canonical source:

```bash
uv tool install "bmad-loop[tui] @ git+https://github.com/bmad-code-org/bmad-loop.git" \
  --with "bmad-loop-adapter-goose @ git+https://github.com/robjgray/bmad-loop-adapter-goose.git"
```

This puts the `bmad-loop` command on your PATH globally, with both
bmad-loop and the goose adapter in the same isolated tool environment —
the entry-point scan finds the adapter automatically.

> **Why `uv tool install` and not `uv sync`?**
> The bmad-loop Quick Start shows `uv sync --extra tui`, which creates a
> project-local venv inside a clone of the bmad-loop repo. That flow has
> no `--with` flag for co-installing a second package (the adapter), and a
> bare `uv pip install` after `uv sync` gets removed on the next sync
> (uv treats it as extraneous). The `uv tool install --with` path is the
> canonical way to co-install a community adapter; it's also what bmad-loop's
> own `docs/cli-adapters.md` recommends. If you need the `uv sync` flow
> (e.g. for development), see [CONTRIBUTING.md](CONTRIBUTING.md) for the
> editable workspace setup.

## Set up a project

### 1. Install the BMAD method (bmm module + skills)

The BMAD-METHOD installer places the upstream skills (`bmad-dev-auto`, the
review hunters) into your project's skill tree:

```bash
npx bmad-method install --yes --modules bmm --tools claude-code
```

This creates `_bmad/`, `.claude/skills/`, and the bmm configuration.

### 2. Initialize bmad-loop with the goose profile

```bash
bmad-loop init --cli goose
```

This installs the bundled `bmad-loop-*` skills (resolve, sweep, setup) into
`.agents/skills/` (the goose profile's skill tree), writes
`.bmad-loop/policy.toml` with `[adapter] name = "goose"`, and sets up
gitignores. No manual policy edit is needed.

### 3. Copy upstream skills to the goose skill tree

The BMAD installer places skills in `.claude/skills/` (the claude-code
tree). The goose profile reads from `.agents/skills/`. You need the
upstream BMAD skills in both trees:

**Linux/macOS:**
```bash
cp -r .claude/skills/bmad-dev-auto .agents/skills/
cp -r .claude/skills/bmad-review-adversarial-general .agents/skills/
cp -r .claude/skills/bmad-review-edge-case-hunter .agents/skills/
```

**Windows (PowerShell):**
```powershell
Copy-Item -Recurse .claude/skills/bmad-dev-auto .agents/skills/
Copy-Item -Recurse .claude/skills/bmad-review-adversarial-general .agents/skills/
Copy-Item -Recurse .claude/skills/bmad-review-edge-case-hunter .agents/skills/
```

> **`bmad-review-verification-gap`:** bmad-loop validate also checks for
> this skill. On BMAD v6.10.0 it may not be installed by the BMAD installer
> (it exists as a v6-shim that forwards to the merged `bmad-review` skill).
> If it's missing from `.claude/skills/`, copy both the shim and
> `bmad-review` from the BMAD-method repo:
> ```bash
> # from a clone of BMAD-METHOD:
> cp -r src/core-skills/v6-shims/bmad-review-verification-gap /path/to/project/.agents/skills/
> cp -r src/core-skills/bmad-review /path/to/project/.agents/skills/
> ```
> This is a BMAD-method installer gap, not a bmad-loop or adapter issue.

### 4. Validate

```bash
bmad-loop validate
```

Expected output:
```
  ok: goose found
  ok: goose: hookless — no hook registration needed
  ok: upstream skills present (bmad-dev-auto + review hunters)
```

The remaining validate failures (sprint-status, multiplexer) are
infrastructure prerequisites, not adapter issues — see the bmad-loop docs.

### 5. Run

```bash
bmad-loop run --dry-run    # print the plan
bmad-loop run              # dispatch sessions through Goose ACP
bmad-loop tui              # dashboard view
```

> **Windows:** Set `PYTHONUTF8=1` in your shell before running bmad-loop
> commands, or the → character in dry-run output will trigger a charmap
> encoding error:
> ```powershell
> $env:PYTHONUTF8 = "1"
> ```

## For development (iterating on the adapter or bmad-loop)

The development loop is documented in [CONTRIBUTING.md](CONTRIBUTING.md):
editable install across both repos, the daily edit cycle, testing, and
the dispatch-check recipe for verifying a bmad-loop change didn't break
the adapter wiring. README stays focused on usage; CONTRIBUTING is for
people working on the adapter or bmad-loop itself.

## How it works

- **Transport:** `stdio-jsonrpc` — spawns `goose acp` as a subprocess and
  drives `initialize` / `session/new` / `session/prompt` over JSON-RPC 2.0
- **Completion:** observed from the `session/prompt` response (`stopReason` +
  `usage`) — no hook scripts required
- **Interactive escalation:** falls back to `goose run --output-format
  stream-json`
- **Profile:** `dialect = "none"` (hookless) — bmad-loop dispatches the
  profile name to the registered adapter factory

The reference for the seam is
[`docs/cli-adapters.md`](https://github.com/robjgray/bmad-loop/blob/feat/cli-adapter-registry-v2/docs/cli-adapters.md)
in the bmad-loop repo.