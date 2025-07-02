#! /usr/bin/env -S uv run --script --quiet
# /// script
# dependencies = [
#   "httpx >= 0.28, < 2",
#   "msgspec >= 0.19, < 2",
#   "platformdirs >= 4, < 5",
#   "structlog >= 25, < 26",
#   "yarl >= 1, < 2",
# ]
# requires-python = ">= 3.11"
# ///

import argparse
import logging
import re
import subprocess as sp
import sys

import httpx
import msgspec
import structlog
from platformdirs import PlatformDirs
from yarl import URL

DIRS = PlatformDirs("dduckdns", "dbohdan")
DUCKDNS_URL = URL("https://www.duckdns.org/update")
CONFIG_FILE = DIRS.user_config_path / "config.toml"
IPV6_URL = "https://ipv6.icanhazip.com"


class DomainSettings(msgspec.Struct, forbid_unknown_fields=True, frozen=True):
    clear: bool = False
    ip: str = ""
    ipv6: str = ""


class Config(msgspec.Struct, forbid_unknown_fields=True, frozen=True):
    token_command: list[str]
    domains: dict[str, DomainSettings]


def boolean(value: bool) -> str:
    return "true" if value else "false"


def get_ipv6() -> str:
    ipv6 = httpx.get(IPV6_URL).text.strip()

    log = structlog.get_logger()
    log.debug("Got IPv6 response", ipv6=ipv6)

    return ipv6


def duckdns(
    token: str,
    domain: str,
    settings: DomainSettings,
    *,
    verbose: bool = False,
) -> None:
    url = DUCKDNS_URL.with_query(
        clear=boolean(settings.clear),
        domains=domain,
        ip=settings.ip,
        ipv6=get_ipv6() if settings.ipv6 == "auto" else settings.ipv6,
        token=token,
        verbose=boolean(verbose),
    )

    log = structlog.get_logger()
    log.debug("Making Duck DNS request", url=url.update_query(token="redacted"))
    text = httpx.get(str(url)).text.strip()
    log.debug("Got Duck DNS response", text=text)

    if not re.match(r"^OK\n", text):
        msg = f"Unexpected response: {text!r}"
        raise ValueError(msg)


def configure_logging(verbose: bool) -> None:
    if sys.stderr.isatty():
        processors = [
            structlog.dev.ConsoleRenderer(
                exception_formatter=structlog.dev.plain_traceback,
            ),
        ]
    else:
        processors = [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if verbose else logging.INFO,
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print debug information",
    )
    args = parser.parse_args()

    config = msgspec.toml.decode(CONFIG_FILE.read_text(), type=Config)
    token = sp.check_output(config.token_command, text=True).strip()

    configure_logging(args.verbose)
    log = structlog.get_logger()

    exit_status = 0
    for domain, settings in config.domains.items():
        try:
            duckdns(token, domain, settings)

        except (httpx.HTTPError, ValueError):
            exit_status = 1
            log.exception("Failed to update domain %r", domain)

    sys.exit(exit_status)


if __name__ == "__main__":
    main()
