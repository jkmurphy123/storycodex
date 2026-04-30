from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_WORLDCODEX_CLI = "world"
DEFAULT_WORLDCODEX_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class WorldCodexClientError(RuntimeError):
    """Raised when a WorldCodex command fails or returns unusable output."""


CommandRunner = Callable[[Sequence[str], int], CommandResult]


def get_worldcodex_world() -> str | None:
    value = os.getenv("STORYCODEX_WORLDCODEX_WORLD")
    if value is None or not value.strip():
        return None
    return value.strip()


def get_worldcodex_cli() -> str:
    return os.getenv("STORYCODEX_WORLDCODEX_CLI", DEFAULT_WORLDCODEX_CLI)


def get_worldcodex_timeout_seconds() -> int:
    raw = os.getenv("STORYCODEX_WORLDCODEX_TIMEOUT_SECONDS")
    if raw is None or raw == "":
        return DEFAULT_WORLDCODEX_TIMEOUT_SECONDS
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("STORYCODEX_WORLDCODEX_TIMEOUT_SECONDS must be an integer") from exc
    if value < 1:
        raise ValueError("STORYCODEX_WORLDCODEX_TIMEOUT_SECONDS must be >= 1")
    return value


def _default_runner(args: Sequence[str], timeout_seconds: int) -> CommandResult:
    completed = subprocess.run(
        list(args),
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout_seconds,
    )
    return CommandResult(
        args=tuple(args),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


class WorldCodexClient:
    def __init__(
        self,
        *,
        world: str | Path,
        cli: str = DEFAULT_WORLDCODEX_CLI,
        timeout_seconds: int = DEFAULT_WORLDCODEX_TIMEOUT_SECONDS,
        runner: CommandRunner | None = None,
    ) -> None:
        self._world = str(world)
        self._cli = cli
        self._timeout_seconds = timeout_seconds
        self._runner = runner or _default_runner

    @property
    def world(self) -> str:
        return self._world

    def export_context(
        self,
        context_type: str,
        *,
        location_id: str = "",
        character_id: str = "",
        faction_id: str = "",
        tag: str = "",
        canon_tier: str = "",
    ) -> dict[str, Any]:
        args = [self._cli, "export", self._world, context_type]
        if location_id:
            args.extend(["--location", location_id])
        if character_id:
            args.extend(["--character", character_id])
        if faction_id:
            args.extend(["--faction", faction_id])
        if tag:
            args.extend(["--tag", tag])
        if canon_tier:
            args.extend(["--canon-tier", canon_tier])

        result = self._run(args)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise WorldCodexClientError(
                f"WorldCodex export returned invalid JSON for context '{context_type}'"
            ) from exc
        if not isinstance(payload, dict):
            raise WorldCodexClientError(
                f"WorldCodex export for context '{context_type}' must return a JSON object"
            )
        return payload

    def validate_patch(self, patch_path: Path) -> CommandResult:
        return self._run_patch_command("validate", patch_path)

    def preview_patch(self, patch_path: Path) -> CommandResult:
        return self._run_patch_command("preview", patch_path)

    def apply_patch(self, patch_path: Path) -> CommandResult:
        return self._run_patch_command("apply", patch_path)

    def _run_patch_command(self, action: str, patch_path: Path) -> CommandResult:
        return self._run([self._cli, "patch", action, self._world, str(patch_path)])

    def _run(self, args: Sequence[str]) -> CommandResult:
        try:
            result = self._runner(args, self._timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            raise WorldCodexClientError(
                f"WorldCodex command timed out after {self._timeout_seconds}s: {' '.join(args)}"
            ) from exc
        except OSError as exc:
            raise WorldCodexClientError(f"Unable to run WorldCodex command: {' '.join(args)}") from exc

        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "no output"
            raise WorldCodexClientError(
                f"WorldCodex command failed with exit code {result.returncode}: {' '.join(args)}\n{detail}"
            )
        return result


def build_worldcodex_client(*, world: str | Path | None = None) -> WorldCodexClient:
    resolved_world = world or get_worldcodex_world()
    if resolved_world is None:
        raise WorldCodexClientError("STORYCODEX_WORLDCODEX_WORLD is required")
    return WorldCodexClient(
        world=resolved_world,
        cli=get_worldcodex_cli(),
        timeout_seconds=get_worldcodex_timeout_seconds(),
    )
