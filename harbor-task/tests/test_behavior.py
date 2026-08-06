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
            "print('stdout-ok', flush=True); "
            "print('stderr-ok', file=sys.stderr, flush=True); "
            "sys.exit(17)"
        )
        first = invoke(
            shell,
            ["--log", str(log), "--", sys.executable, "-c", code, "name with spaces*"],
        )
        second = invoke(
            shell,
            ["--log", str(log), "--", sys.executable, "-c", code, "name with spaces*"],
        )
        assert first.returncode == 17, (shell, first.returncode, first.stderr)
        assert second.returncode == 17, (shell, second.returncode, second.stderr)
        assert log.read_text(encoding="utf-8").splitlines() == [
            "stdout-ok",
            "stderr-ok",
            "stdout-ok",
            "stderr-ok",
        ]


def assert_invalid_usage(shell: str) -> None:
    for args in ([], ["--log"], ["wrong"], ["--",]):
        result = invoke(shell, args)
        assert result.returncode == 64, (shell, args, result.returncode, result.stderr)


def assert_pid_gone(pid_file: Path) -> None:
    assert pid_file.exists(), f"worker pid marker missing: {pid_file}"
    pid = int(pid_file.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        except PermissionError:
            return
        time.sleep(0.02)
    raise AssertionError(f"worker process {pid} survived launcher exit")


def signal_worker_code(marker: Path, exit_code: int, pid_file: Path) -> str:
    return (
        "import os, pathlib, signal, sys, time; "
        f"marker=pathlib.Path({str(marker)!r}); "
        f"pid_file=pathlib.Path({str(pid_file)!r}); pid_file.write_text(str(os.getpid())); "
        f"handler=lambda signum, frame: (marker.write_text(str(signum)), sys.exit({exit_code})); "
        "signal.signal(signal.SIGTERM, handler); signal.signal(signal.SIGINT, handler); "
        "marker.with_suffix('.ready').write_text('ready'); "
        "time.sleep(30)"
    )


def assert_signal_forwarding(shell: str, sig: signal.Signals, expected: int) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        marker = tmp_path / f"handled-{sig.name}.txt"
        pid_file = tmp_path / "worker.pid"
        code = signal_worker_code(marker, expected, pid_file)
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
            assert_pid_gone(pid_file)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=3.0)


def assert_shutdown_timeout(shell: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ready = Path(tmp) / "ignore-ready"
        pid_file = Path(tmp) / "worker.pid"
        code = (
            "import os, pathlib, signal, time; "
        f"ready=pathlib.Path({str(ready)!r}); "
            f"pid_file=pathlib.Path({str(pid_file)!r}); pid_file.write_text(str(os.getpid())); "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "signal.signal(signal.SIGINT, signal.SIG_IGN); "
            "ready.write_text('ready'); time.sleep(30)"
        )
        process = subprocess.Popen(
            [shell, str(LAUNCHER), "--", sys.executable, "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline and not ready.exists():
                time.sleep(0.02)
            assert ready.exists(), f"ignore-worker did not start under {shell}"

            started = time.monotonic()
            process.send_signal(signal.SIGTERM)
            return_code = process.wait(timeout=4.0)
            elapsed = time.monotonic() - started
            assert return_code == 137, (shell, return_code)
            assert elapsed < 3.0, (shell, elapsed)
            assert_pid_gone(pid_file)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=3.0)


def assert_duplicate_signal_suppression(shell: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        marker = tmp_path / "duplicate-signals.txt"
        ready = tmp_path / "ready"
        pid_file = tmp_path / "worker.pid"
        code = (
            "import os, pathlib, signal, sys, time; "
            f"marker=pathlib.Path({str(marker)!r}); ready=pathlib.Path({str(ready)!r}); seen=[]; "
            f"pid_file=pathlib.Path({str(pid_file)!r}); pid_file.write_text(str(os.getpid())); "
            "handler=lambda signum, frame: (seen.append(signal.Signals(signum).name), marker.write_text(','.join(seen)), sys.exit(41) if len(seen) >= 2 else None); "
            "signal.signal(signal.SIGTERM, handler); signal.signal(signal.SIGINT, handler); "
            "ready.write_text('ready'); time.sleep(30)"
        )
        process = subprocess.Popen(
            [shell, str(LAUNCHER), "--", sys.executable, "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline and not ready.exists():
                time.sleep(0.02)
            assert ready.exists(), f"duplicate-signal worker did not start under {shell}"

            started = time.monotonic()
            process.send_signal(signal.SIGTERM)
            time.sleep(0.05)
            process.send_signal(signal.SIGTERM)
            return_code = process.wait(timeout=4.0)
            elapsed = time.monotonic() - started
            assert return_code == 137, (shell, return_code)
            assert elapsed < 3.0, (shell, elapsed)
            assert marker.read_text(encoding="utf-8") == "SIGTERM"
            assert_pid_gone(pid_file)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=3.0)


def assert_graceful_shutdown_window(shell: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        marker = tmp_path / "graceful.txt"
        ready = tmp_path / "ready"
        pid_file = tmp_path / "worker.pid"
        code = (
            "import os, pathlib, signal, sys, time; "
            f"marker=pathlib.Path({str(marker)!r}); ready=pathlib.Path({str(ready)!r}); "
            f"pid_file=pathlib.Path({str(pid_file)!r}); pid_file.write_text(str(os.getpid())); "
            "handler=lambda signum, frame: (marker.write_text('handled'), time.sleep(0.15), sys.exit(45)); "
            "signal.signal(signal.SIGTERM, handler); ready.write_text('ready'); time.sleep(30)"
        )
        process = subprocess.Popen(
            [shell, str(LAUNCHER), "--", sys.executable, "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline and not ready.exists():
                time.sleep(0.02)
            assert ready.exists(), f"graceful worker did not start under {shell}"

            started = time.monotonic()
            process.send_signal(signal.SIGTERM)
            return_code = process.wait(timeout=4.0)
            elapsed = time.monotonic() - started
            assert return_code == 45, (shell, return_code)
            assert 0.08 <= elapsed < 1.50, (shell, elapsed)
            assert marker.read_text(encoding="utf-8") == "handled"
            assert_pid_gone(pid_file)
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
        assert_duplicate_signal_suppression(shell)
        assert_graceful_shutdown_window(shell)
        assert_shutdown_timeout(shell)


if __name__ == "__main__":
    main()
