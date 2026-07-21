"""End-to-end test: `bmad-loop run --story 1-1-a` driven by the goose-acp
stdio-JSON-RPC adapter against a fixture project with a fake `goose` CLI.

Mirrors bmad-loop's test_stories_e2e.py but uses a Python fake CLI that
speaks ACP on stdio — no tmux, no psmux, runs on all platforms. Pins:
(1) goose profile is discoverable via entry-point registry, (2) user-profile
overlay redirects binary, (3) GooseDevAcpAdapter drives the dev session
end-to-end (initialize → session/new → session/prompt → result synthesis
from the id-keyed spec), (4) story commits and exits 0, (5) final story
status is `done`.

Vendors the minimal conftest helpers from bmad-loop's test suite so this
package's tests are self-contained.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# Spec folder + story id the goal asks us to prove. The id is "1-1-a" (Epic 1,
# Story 1, sub-letter "a") — a valid stories-mode id.
SPEC_FOLDER = "_bmad-output/epic-1"
STORY_ID = "1-1-a"
STORY_SLUG = "first-thing"  # derives the spec filename 1-1-a-first-thing.md

SESSION_TIMEOUT_S_ENV = "BMAD_LOOP_SESSION_TIMEOUT_S"
SESSION_TIMEOUT_S = "30"  # seconds

# ---- vendored conftest helpers (from bmad-loop tests/conftest.py) ----

def install_bmad_config(paths) -> None:
    """Write the _bmad/bmm/config.yaml that bmadconfig.load_paths resolves."""
    cfg = paths.project / "_bmad" / "bmm"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "config.yaml").write_text(
        "implementation_artifacts: '{project-root}/_bmad-output/implementation-artifacts'\n"
        "planning_artifacts: '{project-root}/_bmad-output/planning-artifacts'\n"
    )


def _write_skill_stubs(skills: Path, catalog: dict) -> None:
    for skill, markers in catalog.items():
        d = skills / skill
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(f"# {skill}\n", encoding="utf-8")
        for marker in markers:
            (d / marker).write_text("x\n", encoding="utf-8")


def install_dev_base_skills(root: Path, tree: str = ".claude/skills", *, folder_id: bool) -> Path:
    """Lay down stubs of the upstream skills the orchestrator drives on every dev run."""
    from bmad_loop.install import (
        DEV_BASE_SKILLS,
        STORIES_PROBE_FILE,
        STORIES_PROBE_SKILL,
        STORIES_PROBE_TEXT,
    )

    skills = Path(root) / tree
    _write_skill_stubs(skills, DEV_BASE_SKILLS)
    if folder_id:
        (skills / STORIES_PROBE_SKILL / STORIES_PROBE_FILE).write_text(
            f"This is a **{STORIES_PROBE_TEXT}** router.\n", encoding="utf-8"
        )
    return skills


def write_script_launcher(directory: Path, name: str, body: str) -> Path:
    """Write a fake CLI launcher for the host OS."""
    directory = Path(directory)
    sidecar = directory / f"{name}.py"
    sidecar.write_text(body, encoding="utf-8")
    if sys.platform == "win32":
        launcher = directory / f"{name}.cmd"
        launcher.write_text(f'@"{sys.executable}" "{sidecar}" %*\r\n', encoding="utf-8")
    else:
        launcher = directory / name
        launcher.write_text(
            f'#!/bin/sh\nexec "{sys.executable}" "{sidecar}" "$@"\n', encoding="utf-8"
        )
        launcher.chmod(0o755)
    return launcher


# ---- fake goose CLI ----

FAKE_GOOSE = r'''
import json
import os
import subprocess
import sys
import time

def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()

spec_written = set()

def write_story_spec(story_id, spec_folder, baseline):
    stories_dir = os.path.join(spec_folder, "stories")
    os.makedirs(stories_dir, exist_ok=True)
    spec_path = os.path.join(stories_dir, story_id + "-first-thing.md")
    if story_id in spec_written:
        return spec_path
    if not baseline:
        try:
            baseline = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True
            ).strip()
        except Exception:
            baseline = "NO_VCS"
    with open(spec_path, "w", encoding="utf-8") as fh:
        fh.write(
            "---\n"
            "title: 'Story " + story_id + "'\n"
            "status: done\n"
            "baseline_commit: '" + baseline + "'\n"
            "---\n\n"
            "# " + story_id + "\n\nimplemented by fake goose.\n"
        )
    with open("src.txt", "a", encoding="utf-8") as fh:
        fh.write("impl for " + story_id + "\n")
    spec_written.add(story_id)
    return spec_path

baseline = os.environ.get("BMAD_LOOP_BASELINE_COMMIT", "") or ""
story_id = os.environ.get("BMAD_LOOP_STORY_KEY", "")
spec_folder = os.environ.get("BMAD_LOOP_SPEC_FOLDER", "")

for raw_line in sys.stdin:
    line = raw_line.strip()
    if not line:
        continue
    req = json.loads(line)
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        send({"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "v1"}})
    elif method == "session/new":
        send({
            "jsonrpc": "2.0", "id": req_id,
            "result": {"sessionId": "session-fake-1"},
        })
    elif method == "session/prompt":
        sid = req["params"]["sessionId"]
        send({
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": sid,
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"text": "Implemented " + story_id + "."},
                },
            },
        })
        if story_id and spec_folder:
            write_story_spec(story_id, spec_folder, baseline)
        send({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "stopReason": "endTurn",
                "usage": {"totalTokens": 1, "inputTokens": 1, "outputTokens": 0},
            },
        })
    elif method == "session/close":
        send({"jsonrpc": "2.0", "id": req_id, "result": {}})
        time.sleep(30)
        break
'''


def _goose_user_profile(binary_path: str) -> str:
    return f'''
name = "goose"
binary = "{binary_path}"
prompt_template = "{{prompt}}"
usage_parser = "none"
skill_tree = ".agents/skills"
first_run_note = "fake goose for E2E test"

[env]
GOOSE_MODE = "auto"

[hooks]
dialect = "none"
'''


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _scaffold(root: Path) -> None:
    """A committed, clean sandbox ready to run."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "src.txt").write_text("original\n", encoding="utf-8")
    (root / ".gitignore").write_text(".bmad-loop/runs/\n", encoding="utf-8")

    from bmad_loop.bmadconfig import ProjectPaths
    paths = ProjectPaths(
        project=root,
        implementation_artifacts=root / "_bmad-output" / "implementation-artifacts",
        planning_artifacts=root / "_bmad-output" / "planning-artifacts",
    )
    install_bmad_config(paths)
    for sub in ("implementation-artifacts", "planning-artifacts"):
        (root / "_bmad-output" / sub).mkdir(parents=True, exist_ok=True)
        (root / "_bmad-output" / sub / ".keep").write_text("", encoding="utf-8")

    install_dev_base_skills(root, tree=".agents/skills", folder_id=True)

    folder = root / SPEC_FOLDER
    (folder / "stories").mkdir(parents=True)
    (folder / "SPEC.md").write_text("---\ntitle: Epic 1\n---\n# Epic 1\n", encoding="utf-8")
    entries = [{"id": STORY_ID, "title": f"Story {STORY_ID}", "description": "first thing"}]
    (folder / "stories.yaml").write_text(yaml.safe_dump(entries, sort_keys=False), encoding="utf-8")

    bin_dir = root / ".bmad-loop" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    write_script_launcher(bin_dir, "goose", FAKE_GOOSE)
    launcher = bin_dir / ("goose.cmd" if sys.platform == "win32" else "goose")

    profiles = root / ".bmad-loop" / "profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    launcher_path = str(launcher).replace("\\", "/")
    (profiles / "goose.toml").write_text(_goose_user_profile(launcher_path), encoding="utf-8")

    (root / ".bmad-loop" / "policy.toml").write_text(
        '[adapter]\nname = "goose"\n\n'
        "[review]\nenabled = false\n\n"
        f'[stories]\nsource = "stories"\nspec_folder = "{SPEC_FOLDER}"\n',
        encoding="utf-8",
    )

    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "e2e@goose-acp")
    _git(root, "config", "user.name", "e2e goose")
    _git(root, "config", "core.fsync", "none")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "sandbox")


def _commit_count(root: Path) -> int:
    out = subprocess.run(
        ["git", "-C", str(root), "rev-list", "--count", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(out.stdout.strip())


def _run(root: Path, *args: str, timeout: float = 120) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env[SESSION_TIMEOUT_S_ENV] = SESSION_TIMEOUT_S
    return subprocess.run(
        [sys.executable, "-m", "bmad_loop.cli", args[0], "--project", str(root), *args[1:]],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(root),
        env=env,
    )


def _story_status(root: Path) -> str:
    spec = root / SPEC_FOLDER / "stories" / f"{STORY_ID}-{STORY_SLUG}.md"
    if not spec.is_file():
        return "pending"
    for line in spec.read_text(encoding="utf-8").splitlines():
        if line.startswith("status:"):
            return line.split(":", 1)[1].strip().strip("'\"")
    return "?"


@pytest.mark.skipif(
    not os.environ.get("BMAD_LOOP_ADAPTER_GOOSE_E2E"),
    reason="E2E test requires both packages installed; set BMAD_LOOP_ADAPTER_GOOSE_E2E=1 to run",
)
def test_e2e_goose_acp_story_happy_path(tmp_path: Path) -> None:
    """One-story happy path: story reaches `done`, dev session commits, CLI exits 0."""
    root = tmp_path / "sbx-goose"
    _scaffold(root)
    base = _commit_count(root)

    proc = _run(root, "run", "--story", STORY_ID)
    assert proc.returncode == 0, (
        f"bmad-loop run failed (rc={proc.returncode}):\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}\n"
    )
    assert _story_status(root) == "done", (
        f"story {STORY_ID} did not reach done\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}\n"
    )
    assert _commit_count(root) == base + 1, (
        f"expected 1 new commit, got {_commit_count(root) - base}"
    )