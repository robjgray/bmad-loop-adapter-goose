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
- The [BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) installer
  run in your project to install the `bmm` module (provides the
  `bmad-dev-auto` skill and review hunters that the orchestrator drives)

## Install

bmad-loop is not on PyPI — it installs from GitHub. This adapter requires the
CLI adapter entry-point registry, which is currently on a feature branch
pending merge into bmad-loop's `main`. Install both together:

```bash
uv tool install "bmad-loop @ git+https://github.com/robjgray/bmad-loop.git@feat/cli-adapter-registry-v2" \
  --with "bmad-loop-adapter-goose @ git+https://github.com/robjgray/bmad-loop-adapter-goose.git"
```

Once the registry lands in a bmad-loop release, this simplifies to the
maintainer's canonical source:

```bash
uv tool install "bmad-loop @ git+https://github.com/bmad-code-org/bmad-loop.git" \
  --with "bmad-loop-adapter-goose @ git+https://github.com/robjgray/bmad-loop-adapter-goose.git"
```

## Set up a project

```bash
# 1. Initialize bmad-loop with the goose profile
bmad-loop init --cli goose

# 2. Set the adapter name in policy.toml
#    Edit .bmad-loop/policy.toml: change [adapter] name from "claude" to "goose"

# 3. Install the BMAD method (bmm module + skills)
#    Via the BMAD-METHOD installer — see:
#    https://github.com/bmad-code-org/BMAD-METHOD

# 4. Validate
bmad-loop validate
```

`bmad-loop validate` should report:
```
  ok: goose found
  ok: goose: hookless — no hook registration needed
  ok: upstream skills present (bmad-dev-auto + review hunters)
```

Then `bmad-loop run` to dispatch a session through the Goose ACP transport.

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