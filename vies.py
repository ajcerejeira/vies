#!/usr/bin/env -S uv run --script

# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "zeep",
# ]
# ///

"""VIES VAT number validation tool.

This script provides functionality to validate European VAT numbers using the
European Commission's VIES (VAT Information Exchange System) service.

Usage:
    # Validate single VAT number (JSON output to stdout)
    ./vies.py check DE123456789

    # Validate multiple VAT numbers
    ./vies.py check DE123456789 FR12345678901 ES12345678Z

    # Output as CSV
    ./vies.py check --format csv DE123456789

    # Save to file
    ./vies.py check --output results.json DE123456789
    ./vies.py check --format csv --output results.csv DE123456789
"""

import argparse
import csv
import json
import sys
from collections.abc import Generator, Iterable, Iterator
from datetime import date
from typing import Literal, TextIO, TypedDict

import zeep


class VIESResult(TypedDict):
    """Structured response data from the VIES validation service."""

    country_code: str
    vat_number: str
    is_valid: bool
    request_date: date
    name: str
    address: str


type SerializerFormat = Literal["csv", "json"]
"""Supported output formats for serializing validation results."""


def serialize(
    fmt: SerializerFormat,
    items: Iterator[VIESResult],
    output: TextIO,
) -> None:
    """Serialize a VIES validation result to the specified format.

    Args:
        fmt: Output format ('csv' or 'json')
        items: iterator of validation results to serialize
        output: Text stream to write the serialized data to

    """
    match fmt:
        case "csv":
            try:
                first = next(items)
                writer = csv.DictWriter(output, fieldnames=first.keys())
                writer.writeheader()
                writer.writerow(first)
                writer.writerows(items)
            except StopIteration:
                pass
        case "json":
            for item in items:
                json.dump(item, output, default=str)
                output.write("\n")


def check(numbers: Iterable[str]) -> Generator[VIESResult]:
    """Validate VAT numbers using the VIES service.

    Args:
        numbers: Iterable of VAT numbers to validate (format: country code + number)
        fmt: Output format for results ('csv' or 'json')
        output: Text stream to write validation results to

    """
    wsdl = "https://ec.europa.eu/taxation_customs/vies/services/checkVatService.wsdl"
    with zeep.Client(wsdl=wsdl) as client:
        for number in numbers:
            response = client.service.checkVat(
                countryCode=number[:2],
                vatNumber=number[2:],
            )
            yield VIESResult(
                country_code=response.countryCode,
                vat_number=response.vatNumber,
                request_date=response.requestDate,
                is_valid=response.valid,
                name=response.name or "",
                address=" ".join((response.address or "").splitlines()),
            )


def main() -> None:
    """Run the VIES CLI tool."""
    parser = argparse.ArgumentParser(
        prog="vies",
        description="Validate European VAT numbers using the VIES service",
        epilog=(
            "For more information about VIES, visit:"
            "https://ec.europa.eu/taxation_customs/vies/"
        ),
    )
    subparsers = parser.add_subparsers(title="commands", required=True)

    # Build the argument parser for the 'check' command
    check_parser = subparsers.add_parser(
        "check",
        description="validate European VAT numbers using the VIES service",
        help="validate European VAT numbers using the VIES service",
    )
    check_parser.add_argument(
        "numbers",
        nargs="+",
        metavar="VAT_NUMBER",
        help="VAT numbers to validate (format: country code + number)",
    )
    check_parser.add_argument(
        "--format",
        "-f",
        choices=["json", "csv"],
        default="json",
        help="output format for validation results (default: json)",
    )
    check_parser.add_argument(
        "--output",
        "-o",
        nargs="?",
        metavar="FILE",
        type=argparse.FileType("w"),
        default=sys.stdout,
        help="output file for results (default: <stdout>)",
    )
    check_parser.set_defaults(command="check")

    # Parse the CLI arguments and call the chosen command
    match (args := parser.parse_args()).command:
        case "check":
            results = check(args.numbers)
            serialize(args.format, results, args.output)


if __name__ == "__main__":
    main()
