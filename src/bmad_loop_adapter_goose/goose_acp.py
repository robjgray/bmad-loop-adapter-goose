"""Goose CLI adapter using the Agent Client Protocol (ACP) over stdio.

Drives ``goose acp`` (JSON-RPC 2.0 over stdin/stdout) directly as a subprocess,
without a terminal multiplexer. The adapter sends ``initialize``,
``session/new`` and ``session/prompt`` requests, drains ``session/update``
notifications, and observes completion from the ``session/prompt`` response
(``stopReason`` + ``usage``). This is the analog of the hookless HTTP/SSE
path used by ``opencode-http``: no hook scripts are required because the
transport itself carries the completion signal.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from bmad_loop.adapters.base import CodingCLIAdapter, SessionHandle, SessionResult, SessionSpec
from bmad_loop.adapters.generic import _DevSynthesisMixin, _ResultFileMixin
from bmad_loop.adapters.profile import CLIProfile
from bmad_loop.bmadconfig import ProjectPaths

_log = logging.getLogger(__name__)


class AcpError(Exception):
    """ACP server protocol or spawn error."""


class GooseAcpAdapter(_ResultFileMixin, CodingCLIAdapter):
    """Drives ``goose acp`` over stdio JSON-RPC 2.0.

    injection:   "stdio-jsonrpc"  -- prompt goes via session/prompt request
    observation: "rpc-response"   -- stopReason in the prompt response
    state:       "remote"         -- session state lives in the ACP server
    """

    name = "goose-acp"
    injection = "stdio-jsonrpc"
    observation = "rpc-response"
    state = "remote"

    def __init__(
        self,
        run_dir: Path,
        policy: Any,
        profile: CLIProfile,
        extra_args: list[str] | None = None,
        usage_grace_s: float = 0.0,
        stop_without_result_nudges: int | None = None,
        **kwargs: Any,
    ) -> None:
        self.run_dir = run_dir
        self.policy = policy
        self.profile = profile
        self.extra_args = extra_args
        self.usage_grace_s = usage_grace_s
        # Accepted for constructor parity; ACP completion is deterministic
        # (prompt response carries stopReason), so nudges are not meaningful.
        self.stop_without_result_nudges = stop_without_result_nudges
        self.tasks_dir = run_dir / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, tuple[subprocess.Popen, queue.Queue]] = {}
        self._lock = threading.Lock()
        self._request_id = 0
        self._stop_nudges = 0

    def _build_argv(self) -> list[str]:
        return [self.profile.binary, "acp"]

    def _build_env(self, spec: SessionSpec) -> dict[str, str]:
        env = dict(os.environ)
        env.update(self.profile.env)
        env.update(spec.env)
        env.setdefault("GOOSE_MODE", "auto")
        return env

    def _next_id(self) -> int:
        with self._lock:
            self._request_id += 1
            return self._request_id

    @staticmethod
    def _reader_thread(proc: subprocess.Popen, rx_queue: queue.Queue) -> None:
        """Drain stdout lines into ``rx_queue``; ``None`` marks EOF."""
        try:
            for raw_line in proc.stdout or []:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    rx_queue.put(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    # Best-effort: ignore non-JSON noise (tracing, warnings).
                    pass
        finally:
            rx_queue.put(None)

    def _send_request(
        self,
        proc: subprocess.Popen,
        rx_queue: queue.Queue,
        method: str,
        params: dict | None = None,
        *,
        collect_notifications: bool = False,
        timeout_s: float = 120.0,
    ) -> tuple[dict | None, list[dict]]:
        """Send a JSON-RPC request and block until its response arrives.

        Notifications received while waiting are optionally collected.
        """
        req_id = self._next_id()
        request: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "id": req_id}
        if params:
            request["params"] = params

        if proc.stdin is None:
            raise AcpError("ACP subprocess has no stdin pipe")
        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.flush()

        notifications: list[dict] = []
        deadline = time.monotonic() + timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Timed out waiting for response to {method}")
            try:
                msg = rx_queue.get(timeout=remaining)
            except queue.Empty:
                raise TimeoutError(f"Timed out waiting for response to {method}")

            if msg is None:
                # EOF before response.
                raise AcpError(f"ACP stdout closed while waiting for response to {method}")
            if msg.get("id") == req_id:
                return msg, notifications
            if "method" in msg and "id" not in msg:
                if collect_notifications:
                    notifications.append(msg)
                continue
            # Unexpected response message; keep waiting for ours.

    def start_session(self, spec: SessionSpec) -> SessionHandle:
        task_dir = self.tasks_dir / spec.task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "prompt.txt").write_text(spec.prompt + "\n", encoding="utf-8")
        self._read_result(spec.task_id)  # clear any stale result.json

        argv = self._build_argv()
        env = self._build_env(spec)

        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
            cwd=str(spec.cwd),
        )

        # If any RPC handshake step fails, tear down the subprocess so we
        # never leak a lingering ``goose acp`` process (#217).
        try:
            rx_queue: queue.Queue = queue.Queue()
            reader = threading.Thread(
                target=self._reader_thread, args=(proc, rx_queue), daemon=True
            )
            reader.start()

            init_resp, _ = self._send_request(
                proc,
                rx_queue,
                "initialize",
                {
                    "protocolVersion": "v1",
                    "clientCapabilities": {},
                    "clientInfo": {"name": "bmad-loop", "version": "1.0.0"},
                },
                timeout_s=30.0,
            )
            if not init_resp or "result" not in init_resp:
                raise AcpError(f"initialize failed: {init_resp}")

            session_resp, _ = self._send_request(
                proc,
                rx_queue,
                "session/new",
                {"mcpServers": [], "cwd": str(spec.cwd)},
                timeout_s=30.0,
            )
            if not session_resp or "result" not in session_resp:
                raise AcpError(f"session/new failed: {session_resp}")
        except Exception:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
            raise

        session_id = session_resp["result"]["sessionId"]
        launched_ns = time.time_ns()
        with self._lock:
            self._sessions[spec.task_id] = (proc, rx_queue)

        return SessionHandle(
            task_id=spec.task_id,
            native_id=session_id,
            launched_ns=launched_ns,
        )

    def wait_for_completion(self, handle: SessionHandle, spec: SessionSpec) -> SessionResult:
        with self._lock:
            session = self._sessions.get(handle.task_id)
        if session is None:
            return self._final(handle, spec, "crashed", handle.native_id, None)
        proc, rx_queue = session

        try:
            prompt_resp, notifications = self._send_request(
                proc,
                rx_queue,
                "session/prompt",
                {
                    "sessionId": handle.native_id,
                    "prompt": [{"type": "text", "text": spec.prompt}],
                },
                collect_notifications=True,
                timeout_s=spec.timeout_s,
            )
        except TimeoutError:
            return self._final(handle, spec, "timeout", handle.native_id, None)
        except AcpError:
            return self._final(handle, spec, "crashed", handle.native_id, None, accept_result=False)

        if "error" in prompt_resp:
            return self._final(
                handle,
                spec,
                "crashed",
                handle.native_id,
                None,
                accept_result=False,
            )

        result = prompt_resp.get("result", {})
        stop_reason = result.get("stopReason", "")
        usage = result.get("usage", {})

        # Reconstruct the last assistant text from agent_message_chunk notifications.
        last_text = ""
        for n in notifications:
            update = n.get("params", {}).get("update", {})
            if update.get("sessionUpdate") == "agent_message_chunk":
                content = update.get("content", {})
                if isinstance(content, dict):
                    text = content.get("text", "")
                    if text:
                        last_text += text

        result_json = {
            "stopReason": stop_reason,
            "usage": usage,
            "response": last_text,
        }
        result_path = self._result_path(handle.task_id)
        result_path.write_text(json.dumps(result_json, indent=2) + "\n", encoding="utf-8")

        return self._final(handle, spec, "completed", handle.native_id, None)

    def send_text(self, handle: SessionHandle, text: str) -> None:
        """Inject an additional prompt turn.

        Note: ACP has no "append to the current turn" operation; this starts a
        new ``session/prompt`` request. The engine calls this only as a stall
        nudge, so a second prompt turn is the closest available mechanism.
        """
        with self._lock:
            session = self._sessions.get(handle.task_id)
        if session is None:
            return
        proc, rx_queue = session
        try:
            self._send_request(
                proc,
                rx_queue,
                "session/prompt",
                {
                    "sessionId": handle.native_id,
                    "prompt": [{"type": "text", "text": text}],
                },
                collect_notifications=False,
                timeout_s=30.0,
            )
        except (TimeoutError, AcpError) as exc:
            _log.warning("send_text stall nudge failed (non-fatal): %s", exc)

    def kill(self, handle: SessionHandle) -> None:
        with self._lock:
            session = self._sessions.pop(handle.task_id, None)
        if session is None:
            return
        proc, rx_queue = session
        try:
            # Best-effort close; swallow errors because the process may already
            # be gone and we are about to tear it down anyway.
            self._send_request(
                proc,
                rx_queue,
                "session/close",
                {"sessionId": handle.native_id},
                timeout_s=5.0,
            )
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass

    def read_usage(self, result: SessionResult) -> Any:
        if not result.result_json:
            return None
        usage = result.result_json.get("usage", {})
        if not usage:
            return None
        from bmad_loop.model import TokenUsage

        return TokenUsage(
            total_tokens=usage.get("totalTokens"),
            input_tokens=usage.get("inputTokens"),
            output_tokens=usage.get("outputTokens"),
        )

    def interactive_argv(self, spec: SessionSpec) -> list[str]:
        """Interactive escalation falls back to ``goose run`` (ACP has no
        interactive mode); the argv is constructed here, not via launch_args."""
        argv = [
            self.profile.binary,
            "run",
            "--output-format",
            "stream-json",
            "--text",
            self.profile.render_prompt(spec.prompt),
        ]
        if self.extra_args:
            argv.extend(self.extra_args)
        if spec.model:
            argv += [self.profile.model_flag, spec.model]
        return argv

    def interactive_env(self, spec: SessionSpec) -> dict[str, str]:
        return {**self.profile.env, **spec.env}


class GooseDevAcpAdapter(_DevSynthesisMixin, GooseAcpAdapter):
    """Dev/review adapter for the generic ``bmad-dev-auto`` skill over ACP.

    The upstream ``bmad-dev-auto`` skill writes no ``result.json``; its
    outcome lives in the terminal spec it leaves on disk. This adapter inherits
    the ACP transport and reuses :class:`_DevSynthesisMixin` to locate and
    synthesize the legacy result dict, just like ``GenericDevAdapter`` and
    ``OpencodeDevAdapter``.
    """

    def __init__(self, *args, paths: ProjectPaths, **kwargs):
        super().__init__(*args, **kwargs)
        self.paths = paths
        self._configure_dev_knobs()

    def _probe_alive(self, handle: SessionHandle) -> bool | None:
        with self._lock:
            session = self._sessions.get(handle.task_id)
        if session is None:
            return False
        proc, _ = session
        return proc.poll() is None

    def wait_for_completion(self, handle: SessionHandle, spec: SessionSpec) -> SessionResult:
        # Drive the ACP turn first; this writes the ACP response as a
        # result.json, but the dev skill's real output is the spec artifact.
        base_result = super().wait_for_completion(handle, spec)
        if base_result.status != "completed":
            return base_result

        synth = self._result_json(handle, spec, wait=True)
        if synth is not None:
            return SessionResult(
                status="completed",
                result_json=synth,
                session_id=base_result.session_id,
                transcript_path=base_result.transcript_path,
                timeout_fired_at=base_result.timeout_fired_at,
                timeout_expired_clock=base_result.timeout_expired_clock,
                budget_weighted=base_result.budget_weighted,
            )

        # No terminal spec landed within the grace period -> stall.
        return SessionResult(
            status="stalled",
            session_id=base_result.session_id,
            timeout_fired_at=base_result.timeout_fired_at,
            timeout_expired_clock=base_result.timeout_expired_clock,
            budget_weighted=base_result.budget_weighted,
        )