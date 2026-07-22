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
bmad-loop init --cli goose
# edit .bmad-loop/policy.toml: set [adapter] name = "goose"
bmad-loop validate
bmad-loop run
```

`bmad-loop validate` reports the Goose profile and confirms it is hookless
(no hook registration required). Run `bmad-loop run` to dispatch a session
through the Goose ACP transport.

## For development (iterating on the adapter or bmad-loop)

The development loop is documented in [CONTRIBUTING.md](CONTRIBUTING.md):
editable install across both repos, daily edit cycle, testing, the
dispatch-check recipe, and common pitfalls. README stays focused on
usage; CONTRIBUTING is for people working on the adapter or bmad-loop
itself.

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
