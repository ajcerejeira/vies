#!/usr/bin/env -S uv run --script

# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "httpx",
#   "openpyxl",
#   "zeep",
# ]
# ///

"""VIES VAT number validation tool.

This script provides functionality to validate European VAT numbers using the
European Commission's VIES (VAT Information Exchange System) service.

Supports both individual validation via SOAP API and batch validation via REST API.

Usage:
    # Validate single VAT number (JSON output to stdout)
    ./vies.py check DE123456789

    # Validate multiple VAT numbers
    ./vies.py check DE123456789 FR12345678901 ES12345678Z

    # Output as CSV
    ./vies.py check --format csv DE123456789

    # Save to file
    ./vies.py check --format json --output results.json DE123456789
    ./vies.py check --format csv --output results.csv DE123456789

    # Batch validate from file (line-delimited VAT numbers)
    ./vies.py batch input.txt

    # Batch validate with custom settings
    ./vies.py batch --size 50 --delay 2.0 --format csv --output results.csv input.txt

    # Batch validate from stdin
    echo -e "DE123456789\\nFR12345678901" | ./vies.py batch
"""

import argparse
import csv
import json
import sys
import time
from collections.abc import Generator, Iterable, Iterator
from io import BytesIO, StringIO
from itertools import batched
from typing import Literal, TextIO, TypedDict

import httpx
import openpyxl
import zeep


class VIESResult(TypedDict):
    """Structured response data from the VIES validation service."""

    country_code: str
    vat_number: str
    is_valid: bool
    name: str
    address: str


type SerializerFormat = Literal["csv", "json"]
"""Supported output formats for serializing validation results."""


def serialize(
    fmt: SerializerFormat,
    items: Iterator[VIESResult],
    output: TextIO,
) -> None:
    """Serialize VIES validation results to the specified format.

    Args:
        fmt: Output format ('csv' or 'json')
        items: Iterator of validation results to serialize
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


def client(*, timeout: float = 60.0, retries: int = 3) -> httpx.Client:
    """Create an HTTP client configured for the VIES REST API.
    
    Args:
        timeout: Request timeout in seconds
        retries: Number of retry attempts for failed requests
        
    Returns:
        Configured HTTP client for VIES API calls
    """
    return httpx.Client(
        base_url="https://ec.europa.eu/taxation_customs/vies/rest-api/",
        timeout=timeout,
        transport=httpx.HTTPTransport(retries=retries),
        limits=httpx.Limits(max_connections=5),
    )


def check(numbers: Iterable[str]) -> Generator[VIESResult]:
    """Validate VAT numbers using the VIES SOAP service.

    Args:
        numbers: Iterable of VAT numbers to validate (format: country code + number)

    Yields:
        Validation results for each VAT number

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
                is_valid=response.valid,
                name=response.name or "",
                address=" ".join((response.address or "").splitlines()),
            )


def create_batch_job(client: httpx.Client, numbers: Iterable[str]) -> str:
    """Create a batch validation job on the VIES service.
    
    Args:
        client: HTTP client for API requests
        numbers: VAT numbers to validate in batch
        
    Returns:
        Token identifying the created batch job
    """
    # Write the VAT numbers to a in-memory CSV file using VIES APi format
    buffer = StringIO()
    header = ["MS Code", "VAT Number", "Requester MS Code", "Requester VAT Number"]
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows((number[:2], number[2:], None, None) for number in numbers)

    # Upload the in-memory CSV file and return the batch job token
    files = {"fileToUpload": ("upload.csv", buffer.getvalue(), "text/csv")}
    response = client.post("/vat-validation", files=files)
    return response.json()["token"]


def get_batch_job_progress(client: httpx.Client, token: str) -> float:
    """Get the progress percentage of a batch validation job.
    
    Args:
        client: HTTP client for API requests
        token: Batch job token
        
    Returns:
        Progress percentage (0-100)
    """
    response = client.get(f"/vat-validation/{token}")
    return response.json()["percentage"]


def get_batch_job_result(client: httpx.Client, token: str) -> Generator[VIESResult]:
    """Retrieve and parse results from a completed batch validation job.
    
    Args:
        client: HTTP client for API requests
        token: Batch job token
        
    Yields:
        Validation results for each VAT number in the batch
    """
    response = client.get(f"/vat-validation-report/{token}")

    # Parse rhe XLSX content generated by the VIES API
    workbook = openpyxl.load_workbook(BytesIO(response.content))
    rows = workbook.worksheets[0].iter_rows(min_row=2, values_only=True)
    for row in rows:
        yield VIESResult(
            country_code=str(row[0]),
            vat_number=str(row[1]),
            is_valid=str(row[4]) == "YES",
            name=str(row[8]),
            address=" ".join(str(row[9] or "").splitlines()),
        )


def batch(
    numbers: Iterable[str],
    size: int,
    *,
    client: httpx.Client,
    delay: float,
) -> Generator[VIESResult]:
    """Process VAT numbers in batches using the VIES batch API.
    
    Args:
        numbers: VAT numbers to validate
        size: Number of VAT numbers per batch
        client: HTTP client for API requests
        delay: Delay in seconds between API calls
        
    Yields:
        Validation results for each VAT number
    """
    for chunk in batched(numbers, size):
        token = create_batch_job(client, chunk)
        time.sleep(delay)

        while get_batch_job_progress(client, token) < 100:
            time.sleep(delay)

        for result in get_batch_job_result(client, token):
            yield result


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

    # Build the argument parser for the 'batch' command
    batch_parser = subparsers.add_parser(
        "batch",
        description="validate European VAT numbers in batches using the VIES service",
        help="validate European VAT numbers in batches using the VIES service"
    )
    batch_parser.add_argument(
        "input",
        nargs="?",
        metavar="FILE",
        type=argparse.FileType("r"),
        default=sys.stdin,
        help="input file that contains line delimited VAT numbers (defaults to STDIN)",
    )
    batch_parser.add_argument(
        "--output",
        "-o",
        nargs="?",
        metavar="FILE",
        type=argparse.FileType("w"),
        default=sys.stdout,
        help="output file to write the results to (defaults to STDOUT)",
    )
    batch_parser.add_argument(
        "--format",
        "-f",
        choices=["json", "csv"],
        default="json",
        help="output format for validation results (default: json)",
    )
    batch_parser.add_argument(
        "--size",
        "-s",
        metavar="SIZE",
        type=int,
        default=99,
        help="batch size for processing multiple VAT numbers (defaults to 99)",
    )
    batch_parser.add_argument(
        "--retries",
        "-r",
        metavar="NUMBER",
        type=int,
        default=3,
        help="number of retry attempts for failed requests (defaults to 3)",
    )
    batch_parser.add_argument(
        "--delay",
        "-d",
        metavar="SECONDS",
        type=float,
        default=5.0,
        help="delay in seconds between batch API calls (defaults to 5.0)",
    )
    
    batch_parser.set_defaults(command="batch")

    # Parse the CLI arguments and call the chosen command
    match (args := parser.parse_args()).command:
        case "check":
            results = check(args.numbers)
            serialize(args.format, results, args.output)
        case "batch":
            with client(timeout=60.0, retries=args.retries) as vies:
                numbers = (number.strip() for number in args.input)
                results = batch(numbers, args.size, client=vies, delay=args.delay)
                serialize(args.format, results, args.output)


if __name__ == "__main__":
    main()
