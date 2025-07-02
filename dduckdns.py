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

VERBOSITY_LOGGING_DEBUG = 1
VERBOSITY_DUCKDNS_VERBOSE = 2


class DomainSettings(msgspec.Struct, forbid_unknown_fields=True, frozen=True):
    clear: bool = False
    ip: str = ""
    ipv6: str = ""


class Config(msgspec.Struct, forbid_unknown_fields=True, frozen=True):
    token_command: list[str]
    domains: dict[str, DomainSettings]


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
        domains=domain,
        ip=settings.ip,
        ipv6=get_ipv6() if settings.ipv6 == "auto" else settings.ipv6,
        token=token,
    )
    if settings.clear:
        url = url.update_query(clear="true")
    # The key `verbose` with any value causes a verbose reponse.
    if verbose:
        url = url.update_query(verbose="true")

    log = structlog.get_logger()
    log.debug("Making Duck DNS request", url=url.update_query(token="redacted"))  # noqa: S106
    text = httpx.get(str(url)).text.strip()
    log.debug("Got Duck DNS response", text=text)

    if not re.match(r"^OK(?:\n|$)", text):
        msg = f"Unexpected response: {text!r}"
        raise ValueError(msg)


def configure_logging(verbosity: int) -> None:
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
            logging.DEBUG if verbosity >= VERBOSITY_LOGGING_DEBUG else logging.INFO,
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        dest="verbosity",
        help="print debug information",
    )
    args = parser.parse_args()

    config = msgspec.toml.decode(CONFIG_FILE.read_text(), type=Config)
    token = sp.check_output(config.token_command, text=True).strip()

    configure_logging(args.verbosity)
    log = structlog.get_logger()

    exit_status = 0
    for domain, settings in config.domains.items():
        try:
            duckdns(
                token,
                domain,
                settings,
                verbose=args.verbosity >= VERBOSITY_DUCKDNS_VERBOSE,
            )

        except (httpx.HTTPError, ValueError):
            exit_status = 1
            log.exception("Failed to update domain %r", domain)

    sys.exit(exit_status)


if __name__ == "__main__":
    main()
