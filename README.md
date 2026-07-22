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

The fast loop is to install both repos as editable so edits are picked up
without reinstalling. The trick is `uv tool install -e` plus
`--with-editable` for the other package, so the `bmad-loop` shim resolves
entry points through the editable site-packages:

```bash
# 1. Clone both repos side by side
git clone https://github.com/bmad-code-org/bmad-loop
git clone https://github.com/robjgray/bmad-loop-adapter-goose

# 2. In the adapter repo, check out the bmad-loop branch that ships the
#    registry (currently feat/cli-adapter-registry-v2 on the bmad-loop side).
cd bmad-loop && git checkout feat/cli-adapter-registry-v2 && cd ..

# 3. Install bmad-loop as an editable tool, with the adapter as a
#    co-installed editable
uv tool install -e ./bmad-loop --with-editable ./bmad-loop-adapter-goose
```

After this, edits in either repo's `src/` are visible to the `bmad-loop`
shim on the next run — no reinstall loop. The shim's entry-point scan
re-runs every time the tool starts, so a freshly added adapter or a
changed factory shows up immediately.

If bmad-loop is *not* checked out at a branch that has the registry
(`bmad_loop.adapters.registry`), the adapter's import will fail at
entry-point load time. `bmad-loop validate` surfaces the failure as
`warning: external adapter 'goose' failed to load: <reason>` — install
the registry-bearing branch to clear it.

To uninstall:

```bash
uv tool uninstall bmad-loop
```

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
