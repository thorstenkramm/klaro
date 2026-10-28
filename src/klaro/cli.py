"""Command-line launcher for the packaged Klaro Gunicorn service."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from klaro.config import ConfigError, load_config


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="klaro",
        description="Validate Klaro's TOML configuration and start the Gunicorn service.",
    )
    parser.add_argument(
        "-c",
        "--config",
        required=True,
        type=Path,
        metavar="PATH",
        help="path to the Klaro TOML configuration",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Validate configuration and replace this process with packaged Gunicorn."""
    parser = _parser()
    arguments = parser.parse_args(argv)
    config_path = arguments.config.expanduser().resolve()
    try:
        load_config(config_path)
    except ConfigError as exc:
        parser.error(str(exc))

    os.environ["KLARO_CONFIG"] = str(config_path)
    command = [
        sys.executable,
        "-m",
        "gunicorn",
        "--config",
        "python:klaro.gunicorn_conf",
        "klaro.app:create_app()",
    ]
    try:
        # Replaces this process with the packaged Gunicorn; arguments are fixed, not user input.
        os.execv(sys.executable, command)  # noqa: S606
    except OSError as exc:
        parser.exit(1, f"klaro: could not start Gunicorn: {exc}\n")


if __name__ == "__main__":
    main()
