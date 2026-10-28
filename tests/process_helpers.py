from __future__ import annotations

import os
import signal
import subprocess
import time

import requests

READINESS_PATH = "/static/vendor/htmx/htmx.min.js"


def wait_until_serving(
    process: subprocess.Popen, base_url: str, *, timeout: float = 20, poll: float = 0.1
) -> None:
    """Poll a real server subprocess until it serves a static asset.

    Polling is the only option for an external process; it stops as soon as the
    process exits or the asset is served.
    """
    deadline = time.monotonic() + timeout
    while True:
        if process.poll() is not None:
            raise AssertionError(f"Server exited early with {process.returncode}")
        try:
            if requests.get(f"{base_url}{READINESS_PATH}", timeout=0.5).status_code == 200:
                return
        except requests.RequestException:
            pass
        if time.monotonic() >= deadline:
            raise AssertionError(f"Server did not start within {timeout:g} seconds")
        time.sleep(poll)


def stop_process_group(process: subprocess.Popen | None) -> None:
    """Terminate a server started with ``start_new_session=True``, then force if needed."""
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
