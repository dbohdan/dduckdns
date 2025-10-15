#! /usr/bin/env python3

# SPDX-FileCopyrightText: 2025 D. Bohdan
# SPDX-License-Identifier: MIT
#
# dduckdns - A client for the Duck DNS dynamic DNS service
# https://github.com/dbohdan/dduckdns

import argparse
import json
import logging
import os
import re
import subprocess as sp
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen


def xdg_config_home() -> Path:
    if env_var := os.environ.get("XDG_CONFIG_HOME"):
        return Path(env_var)

    # Handle Windows.
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")

        if appdata:
            return Path(appdata)

        return Path.home() / "AppData" / "Roaming"

    # POSIX systems.
    return Path.home() / ".config"


APP_NAME = "dduckdns"
DEFAULT_CONFIG_FILE = xdg_config_home() / APP_NAME / "config.toml"
VERSION = "0.2.0"

DUCKDNS_URL = "https://www.duckdns.org/update"
IPV6_URL = "https://ipv6.icanhazip.com"

VERBOSITY_LOGGING_DEBUG = 1
VERBOSITY_DUCKDNS_VERBOSE = 2

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DomainSettings:
    clear: bool = False
    ip: str = ""
    ipv6: str = ""


@dataclass(frozen=True)
class Config:
    token_command: list[str]
    domains: dict[str, DomainSettings]


def get_ipv6() -> str:
    with urlopen(IPV6_URL) as response:
        ipv6 = response.read().decode("utf-8").strip()

    logger.debug("Got IPv6 response: %s", ipv6)

    return ipv6


def duckdns(
    token: str,
    domain: str,
    settings: DomainSettings,
    *,
    verbose: bool = False,
) -> None:
    query_params = {
        "domains": domain,
        "ip": settings.ip,
        "ipv6": get_ipv6() if settings.ipv6 == "auto" else settings.ipv6,
        "token": token,
    }
    if settings.clear:
        query_params["clear"] = "true"
    # The key `verbose` with any value causes a verbose reponse.
    if verbose:
        query_params["verbose"] = "true"

    debug_query_params = query_params.copy()
    debug_query_params["token"] = "redacted"
    debug_url = f"{DUCKDNS_URL}?{urlencode(debug_query_params)}"
    logger.debug("Making Duck DNS request: %s", debug_url)

    url = f"{DUCKDNS_URL}?{urlencode(query_params)}"
    with urlopen(url) as response:
        text = response.read().decode("utf-8").strip()
    logger.debug("Got Duck DNS response: %s", text)

    if not re.match(r"^OK(?:\n|$)", text):
        msg = f"Unexpected response: {text!r}"
        raise ValueError(msg)


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        if record.stack_info:
            log_record["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(log_record)


def configure_logging(verbosity: int) -> None:
    handler = logging.StreamHandler(sys.stderr)

    if sys.stderr.isatty():
        formatter = logging.Formatter("%(levelname)s: %(message)s")
    else:
        formatter = JSONFormatter()

    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(
        logging.DEBUG if verbosity >= VERBOSITY_LOGGING_DEBUG else logging.INFO,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"dduckdns {VERSION}",
        help="show version information and exit",
    )
    parser.add_argument(
        "-c",
        "--config",
        default=DEFAULT_CONFIG_FILE,
        type=Path,
        help=f"config file path (default: {str(DEFAULT_CONFIG_FILE)!r})",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        dest="verbosity",
        help="print debug information",
    )
    args = parser.parse_args()

    configure_logging(args.verbosity)

    try:
        config_data = tomllib.loads(args.config.read_text())
        domains = {
            name: DomainSettings(**settings)
            for name, settings in config_data.get("domains", {}).items()
        }
        config = Config(
            token_command=config_data["token_command"],
            domains=domains,
        )
    except FileNotFoundError:
        logger.critical("Config file not found: %s", args.config)
        sys.exit(1)
    except (tomllib.TOMLDecodeError, KeyError, TypeError) as e:
        logger.critical("Failed to parse config file %s: %s", args.config, e)
        sys.exit(1)

    token = sp.check_output(config.token_command, text=True).strip()

    exit_status = 0
    for domain, settings in config.domains.items():
        try:
            duckdns(
                token,
                domain,
                settings,
                verbose=args.verbosity >= VERBOSITY_DUCKDNS_VERBOSE,
            )

        except (URLError, ValueError):
            exit_status = 1
            logger.exception("Failed to update domain %r", domain)

    sys.exit(exit_status)


if __name__ == "__main__":
    main()
