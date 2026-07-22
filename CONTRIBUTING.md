# Contributing to bmad-loop-adapter-goose

This document is for people developing the adapter. For *using* the
adapter (installing it, configuring a project to use it), see the
[README](README.md).

## First-time setup

The fast loop is to install both repos as editable so edits are picked up
without reinstalling. The trick is `uv tool install -e` plus
`--with-editable` for the other package, so the `bmad-loop` shim resolves
entry points through the editable site-packages:

```bash
# 1. Clone both repos side by side
git clone https://github.com/bmad-code-org/bmad-loop
git clone https://github.com/robjgray/bmad-loop-adapter-goose

# 2. In the bmad-loop repo, check out the branch that ships the registry
#    (currently feat/cli-adapter-registry-v2 on the bmad-loop side).
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

## Daily loop: editing across both repos

Once the editable install is in place, the cross-repo edit loop is:

1. **Edit in either repo's `src/`.** No `pip install`, no `uv sync`, no
   `uv tool install --force` — the shim resolves to the editable `.pth`
   files in the tool venv, which point at the source dirs.
2. **Restart `bmad-loop`.** Each invocation re-runs the entry-point
   scan; both your factory changes and your profile TOML changes are
   picked up.
3. **Validate.** `bmad-loop validate --project <something>` is the
   right read-after-write check. It exercises profile discovery,
   adapter registration, the binary-on-PATH check, and the
   hookless/hooked gate.

For adapter-only changes (`goose_acp.py`, the TOML, the entry-point
registration) the loop is just: edit → restart → validate.

For bmad-loop changes (`registry.py`, `cli.py`, the engine) the loop is:
edit → restart → validate. If the change broke the adapter contract
(e.g. signature of a `CodingCLIAdapter` base method, fields on
`CLIProfile`, the `get_cli_adapter` API), the adapter's unit tests in
`tests/test_goose_acp.py` should catch it on the next run; fix the
adapter to match the new contract. The bmad-loop repo's own tests
(`tests/test_cli.py`, `tests/test_opencode_http.py`,
`tests/test_cli_adapter_registry.py`) catch engine-side regressions.

## Testing

The adapter's unit tests use a fake ACP server (a small Python script
that speaks JSON-RPC 2.0) and exercise the full session lifecycle:
`initialize` → `session/new` → `session/prompt` → `result.json`
write → `session/close`. They are real subprocess-based tests, not
stubs.

To run them, use the bmad-loop repo's `.venv` (which has `pytest`
installed):

```bash
cd ../bmad-loop
.venv/Scripts/python.exe -m pytest ../bmad-loop-adapter-goose/tests/test_goose_acp.py
```

The e2e test (`tests/test_stories_e2e_goose.py`) is gated by
`BMAD_LOOP_ADAPTER_GOOSE_E2E=1` and requires a real `bmad-loop run` to
complete — it needs a configured Goose provider and a real story
spec. It's not part of the daily loop; run it when you're preparing a
release or verifying a change that touches the full run path.

## Sanity check: dispatch still maps roles correctly

After a bmad-loop change, confirm the registry still maps each role to
the right adapter class. The expected output is `GooseDevAcpAdapter`
for dev/review (because they run `bmad-dev-auto`, which writes no
`result.json`, so the adapter synthesizes one) and `GooseAcpAdapter`
for triage:

```python
# in any python with both bmad-loop and the adapter installed:
from pathlib import Path
import bmad_loop.policy as policy_mod
from bmad_loop.cli import _make_adapters
project = Path(".../your-project")
pol = policy_mod.load(project / ".bmad-loop" / "policy.toml")
run_dir = project / ".bmad-loop" / "runs" / "test"
run_dir.mkdir(parents=True, exist_ok=True)
adapters = _make_adapters(project, run_dir, pol)
for key, adapter in adapters.items():
    print(f"{key}: {type(adapter).__name__}")
```

Expected:

```
dev: GooseDevAcpAdapter
review: GooseDevAcpAdapter
triage: GooseAcpAdapter
```

If you see the opencode-http classes instead, the registry isn't picking
up the adapter — the validate output will say
`warning: external adapter 'goose' failed to load: <reason>`.

## Reference

- The seam contract is documented in
  [`docs/cli-adapters.md`](https://github.com/bmad-code-org/bmad-loop/blob/main/docs/cli-adapters.md)
  in the bmad-loop repo.
- The entry-point group is `bmad_loop.cli_adapters`. The
  `register_cli_adapter(profile_name="goose", ...)` call lives in
  `src/bmad_loop_adapter_goose/__init__.py` and runs at import time.
- The bmad-loop maintainer's framing: the registry is a *seam* for
  community adapters, not a place to add in-tree adapters. Changes to
  the engine itself should be necessary, YAGNI, and not over-abstracted
  for a single use case. When in doubt, follow the
  `bmad_loop.mux_backends` precedent (same shape, terminal-multiplexer
  backends).
