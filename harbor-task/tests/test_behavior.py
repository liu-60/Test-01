#!/usr/bin/env python3
"""Black-box checks for the backend launcher compatibility contract."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(os.environ.get("TASK_APP_ROOT", "/app/backend"))
LAUNCHER = ROOT / "launch-worker.sh"


def available_shells() -> list[str]:
    candidates = ["/bin/sh", "/usr/bin/dash", "/bin/dash"]
    return [path for path in candidates if Path(path).exists()]


def invoke(shell: str, args: list[str], timeout: float = 5.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [shell, str(LAUNCHER), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def assert_syntax(shell: str) -> None:
    result = subprocess.run(
        [shell, "-n", str(LAUNCHER)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=3,
    )
    assert result.returncode == 0, f"{shell} syntax check failed: {result.stderr}"


def assert_normal_exit_and_argv(shell: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "log file with spaces.log"
        code = (
            "import sys; "
            "assert sys.argv[1] == 'name with spaces*', sys.argv[1]; "
            "print('argv-ok'); sys.exit(17)"
        )
        result = invoke(
            shell,
            ["--log", str(log), "--", sys.executable, "-c", code, "name with spaces*"],
        )
        assert result.returncode == 17, (shell, result.returncode, result.stderr)
        assert log.read_text(encoding="utf-8").strip() == "argv-ok"


def assert_invalid_usage(shell: str) -> None:
    for args in ([], ["--log"], ["wrong"], ["--",]):
        result = invoke(shell, args)
        assert result.returncode == 64, (shell, args, result.returncode, result.stderr)


def signal_worker_code(marker: Path, exit_code: int) -> str:
    return (
        "import pathlib, signal, sys, time; "
        f"marker=pathlib.Path({str(marker)!r}); "
        f"handler=lambda signum, frame: (marker.write_text(str(signum)), sys.exit({exit_code})); "
        "signal.signal(signal.SIGTERM, handler); signal.signal(signal.SIGINT, handler); "
        "marker.with_suffix('.ready').write_text('ready'); "
        "time.sleep(30)"
    )


def assert_signal_forwarding(shell: str, sig: signal.Signals, expected: int) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        marker = tmp_path / f"handled-{sig.name}.txt"
        code = signal_worker_code(marker, expected)
        process = subprocess.Popen(
            [shell, str(LAUNCHER), "--", sys.executable, "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            ready = marker.with_suffix(".ready")
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline and not ready.exists():
                time.sleep(0.02)
            assert ready.exists(), f"worker did not start under {shell}"

            process.send_signal(sig)
            return_code = process.wait(timeout=5.0)
            assert return_code == expected, (shell, sig, return_code)
            assert marker.read_text(encoding="utf-8") == str(sig.value)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=3.0)


def main() -> None:
    assert LAUNCHER.is_file(), f"missing launcher: {LAUNCHER}"
    shells = available_shells()
    assert len(shells) >= 2, f"expected /bin/sh and dash, found {shells}"
    for shell in shells:
        assert_syntax(shell)
        assert_normal_exit_and_argv(shell)
        assert_invalid_usage(shell)
        assert_signal_forwarding(shell, signal.SIGTERM, 42)
        assert_signal_forwarding(shell, signal.SIGINT, 43)


if __name__ == "__main__":
    main()
