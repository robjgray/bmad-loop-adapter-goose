"""Goose CLI adapter for bmad-loop — registers via entry points.

Importing this module runs register(), which calls
register_cli_adapter to register the Goose ACP adapter factories for the
"goose" profile name and the bundled goose profile TOML. The entry-point
group bmad_loop.cli_adapters triggers this import at adapter-load time.
"""

from __future__ import annotations

from .goose_acp import GooseAcpAdapter, GooseDevAcpAdapter


def register() -> None:
    """Register the Goose adapter and profile with bmad-loop's registry."""
    from bmad_loop.adapters.registry import register_cli_adapter

    register_cli_adapter(
        profile_name="goose",
        base_factory=GooseAcpAdapter,
        dev_factory=GooseDevAcpAdapter,
        profile_package="bmad_loop_adapter_goose.profiles",
        profile_filename="goose.toml",
    )


# Self-register at import time (the entry-point loader imports this module).
register()
