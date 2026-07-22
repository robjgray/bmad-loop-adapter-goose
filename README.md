# bmad-loop-adapter-goose

Community CLI adapter for [bmad-loop](https://github.com/bmad-code-org/bmad-loop)
that drives [Goose](https://github.com/aaif-goose/goose) over the Agent Client
Protocol (ACP) on stdio (`goose acp`).

The adapter registers itself via the `bmad_loop.cli_adapters` entry-point
group, so no manual configuration step is needed — once co-installed,
bmad-loop discovers the Goose profile and adapter automatically.

## For users (after the registry lands in a release)

```bash
uv tool install "bmad-loop" \
  --with "bmad-loop-adapter-goose @ git+https://github.com/robjgray/bmad-loop-adapter-goose.git"
```

Then in your project:

```bash
# bmad-loop init's --cli flag accepts any profile name the registry
# can resolve. "goose" is registered by this adapter package via the
# bmad_loop.cli_adapters entry-point group — not a first-party profile
# name in bmad-loop. The init writes the bundled bmad-loop-* skills
# (always wanted) and a hook script (a no-op for the hookless goose
# profile; harmless).
bmad-loop init --cli goose

# In .bmad-loop/policy.toml, set the [adapter] name to "goose" — the
# same value the registry can resolve, so the orchestrator dispatches
# to the GooseDevAcpAdapter (dev/review) or GooseAcpAdapter (triage).
# edit .bmad-loop/policy.toml: set [adapter] name = "goose"

bmad-loop validate
bmad-loop run
```

`bmad-loop validate` reports the Goose profile (via the entry-point
scan) and confirms it is hookless — no hook registration required, no
`httpx` check forced (the adapter manages its own dependencies). Run
`bmad-loop run` to dispatch a session through the Goose ACP transport.

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
[`docs/cli-adapters.md`](https://github.com/bmad-code-org/bmad-loop/blob/main/docs/cli-adapters.md)
in the bmad-loop repo.
