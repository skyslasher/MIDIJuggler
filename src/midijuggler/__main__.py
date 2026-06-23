"""Command line entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import logging

from midijuggler.service import run_from_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the MIDIJuggler service")
    parser.add_argument(
        "--config",
        default="/etc/midijuggler/config.toml",
        help="Path to the TOML configuration file",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        help="Python logging level",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run_from_config(args.config))


if __name__ == "__main__":
    main()
