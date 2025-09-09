#!/usr/bin/env python3

import argparse
import json
import re
import sys
import time
from base64 import b64encode
from functools import wraps
from typing import Callable, Iterable, Iterator
from urllib.request import Request
from urllib.response import addinfourl as Response


type JSON = None | bool | int | float | str | list[JSON] | dict[str, JSON]
"""Type alias for `json` serializable values."""


def flatten(
    data: JSON,
    *,
    delimiter: str = ".",
    prefix: str = "",
) -> Iterable[tuple[str, None | bool | int | float | str]]:
    """Flatten nested JSON object into key-value pairs with delimiter-separated keys.

    Args:
        data: JSON-serializable data structure to flatten (`dict`, `list`, or scalar)
        delimiter: String used to separate nested keys
        prefix: Internal parameter for recursion, specifies key prefix

    Yields:
        Key-value pairs where keys are delimiter-separated paths to leaf values

    Examples:
        Basic dictionary flattening::

        >>> data = {"user": {"name": "John", "age": 30}}
        >>> dict(flatten(data))
        {'user.name': 'John', 'user.age': 30}

        List flattening with indices::

        >>> data = {"users": ["Alice", "Bob"]}
        >>> dict(flatten(data))
        {'users.0': 'Alice', 'users.1': 'Bob'}

        Complex nested structure::

        >>> data = {
        ...     "company": {
        ...         "name": "Acme Corp",
        ...         "employees": [
        ...             {"name": "Alice", "role": "dev"},
        ...             {"name": "Bob", "role": "qa"}
        ...         ]
        ...     },
        ...     "active": True
        ... }
        >>> dict(flatten(data))             # doctest: +ELLIPSIS
        {'company.name': 'Acme Corp', 'company.employees.0.name': 'Alice', ...}

        Custom delimiter::

        >>> data = {"user": {"profile": {"email": "user@example.com"}}}
        >>> dict(flatten(data, delimiter="/"))
        {'user/profile/email': 'user@example.com'}

        Scalar values (no flattening needed)::

        >>> dict(flatten("hello"))
        {'': 'hello'}
        >>> dict(flatten(42))
        {'': 42}

    """
    if isinstance(data, dict):
        for key, value in data.items():
            key = f"{prefix}{delimiter}{key}" if prefix else key
            yield from flatten(value, delimiter=delimiter, prefix=key)
    elif isinstance(data, list):
        for index, value in enumerate(data):
            key = f"{prefix}{delimiter}{index}" if prefix else str(index)
            yield from flatten(value, delimiter=delimiter, prefix=key)
    else:
        yield (prefix, data)


def retry[**P, T](
    exceptions: tuple[type[Exception], ...],
    retries: int = 1,
    *,
    delay: float = 1.0,
    backoff: float = 1.0,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Retry decorator with exponential backoff for handling transient failures.

    Automatically retries function calls when specified exceptions occur, with
    configurable delay and exponential backoff between attempts.

    Args:
        exceptions: Tuple of exception types to catch and retry on.
        retries: Non-negative number of retry attempts after the initial call.
        delay: Initial delay between retries in seconds.
        backoff: Multiplier applied to delay after each failed attempt.

    Returns:
        A decorator function that wraps the target function with retry logic.

    Raises:
        The original exception if all retry attempts are exhausted or if an
        exception type not in the exceptions tuple is encountered.

    Examples:
        Basic usage::

            >>> @retry((ValueError,), retries=2)
            ... def parse_number(text):
            ...     return int(text)

        With exponential backoff::

            >>> @retry((ConnectionError,), retries=3, delay=0.5, backoff=2.0)
            ... def connect():
            ...     # Will retry with delays: 0.5s, 1.0s, 2.0s
            ...     pass

        Multiple exception types::

            >>> @retry((ValueError, TypeError), retries=2)
            ... def process_data(data):
            ...     return data.strip().upper()

    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            current_delay = delay
            for attempt in range(retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as error:
                    if isinstance(error, exceptions) and attempt < retries:
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        raise
            raise RuntimeError("Retry logic error: this should never be reached")

        return wrapper

    return decorator


type RequestFactory = Callable[..., Request]
"""Type alias for factory functions that create HTTP request objects."""

type ResponseParser[T] = Callable[
    [Response],
    Iterator[T | tuple[Request, ResponseParser[T]]],
]
"""Type alias for response parsers that yield data items or follow requests."""


def request(
    path: str,
    body: JSON = None,
    *,
    base_url: str = "https://viesapi.eu/api",
    username: str,
    password: str,
) -> Request:
    """Construct an authenticated HTTP `urllib.request.Request` object for VIES API.

    Args:
        path: The API endpoint path to append to the base URL.
        body: `json` serializable data to include in the request body.
        base_url: The base URL of the VIES API service.
        username: Username for HTTP Basic Authentication.
        password: Password for HTTP Basic Authentication.

    Returns:
        A configured request object ready for use with `urllib.request.urlopen`.

    Examples:
        Create a simple GET request to the VIES test API instance::

        >>> req = request(
        ...     "/check/account/status",
        ...     base_url="https://viesapi.eu/api-test",
        ...     username="test_id",
        ...     password="test_key")
        >>> req.get_full_url()
        'https://viesapi.eu/api-test/check/account/status'
        >>> req.headers["Accept"]
        'application/json'
        >>> req.headers["Authorization"]    # doctest: +ELLIPSIS
        'Basic ...'

        Create a POST request with JSON data::

        >>> req = request(
        ...     "/batch/vies",
        ...     body={"batch": {"numbers": ["FI23064613", "SI51510847", "IE8251135U"]}},
        ...     base_url="https://viesapi.eu/api-test",
        ...     username="test_id",
        ...     password="test_key")
        >>> req.headers["Content-type"]
        'application/json'
        >>> req.data is not None
        True

    """
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    data = None
    auth = b64encode(f"{username}:{password}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Accept": "application/json",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-type"] = "application/json"
    return Request(url, data, headers)


def parse_vat_number(vat_number: str) -> str | None:
    """Parse and validate a VAT number according to country specific formats.

    Args:
        vat_number: The VAT number to parse, containing the two-letter country prefix.

    Returns:
        The sanitized VAT number, or ``None`` if the VAT number is invalid.

    Examples:
        >>> parse_vat_number("PT501613897")
        'PT501613897'

        >>> parse_vat_number("DE 123-456.789")
        'DE123456789'

        >>> parse_vat_number("")

        >>> parse_vat_number("ZZ1234")

    """
    if not vat_number:
        return None

    # fmt:off
    vat_patterns = {
        "AT": r"^U[0-9]{8}$",                   # Austria
        "BE": r"^[0-1][0-9]{9}$",               # Belgium
        "BG": r"^[0-9]{9,10}$",                 # Bulgaria
        "CY": r"^[0-9]{8}[A-Z]$",               # Cyprus
        "CZ": r"^[0-9]{8,10}$",                 # Czech Republic
        "DE": r"^[0-9]{9}$",                    # Germany
        "DK": r"^[0-9]{8}$",                    # Denmark
        "EE": r"^[0-9]{9}$",                    # Estonia
        "EL": r"^[0-9]{9}$",                    # Greece
        "ES": r"^[A-Z0-9][0-9]{7}[A-Z0-9]$",    # Spain
        "FI": r"^[0-9]{8}$",                    # Finland
        "FR": r"^[A-Z0-9]{2}[0-9]{9}$",         # France
        "HR": r"^[0-9]{11}$",                   # Croatia
        "HU": r"^[0-9]{8}$",                    # Hungary
        "IE": r"^[A-Z0-9]{7}[A-Z]{1,2}$",       # Ireland
        "IT": r"^[0-9]{11}$",                   # Italy
        "LT": r"^([0-9]{9}|[0-9]{12})$",        # Lithuania
        "LU": r"^[0-9]{8}$",                    # Luxembourg
        "LV": r"^[0-9]{11}$",                   # Latvia
        "MT": r"^[0-9]{8}$",                    # Malta
        "NL": r"^[0-9]{9}B[0-9]{2}$",           # Netherlands
        "PL": r"^[0-9]{10}$",                   # Poland
        "PT": r"^[0-9]{9}$",                    # Portugal
        "RO": r"^[0-9]{2,10}$",                 # Romania
        "SE": r"^[0-9]{12}$",                   # Sweden
        "SI": r"^[0-9]{8}$",                    # Slovenia
        "SK": r"^[0-9]{10}$",                   # Slovakia
        "GB": r"^([0-9]{9}|[0-9]{12})$",        # United Kingdom
    }
    # fmt:on
    sanitized_vat_number = re.sub(r"[\s\.\-]", "", str(vat_number).upper())
    country_code = sanitized_vat_number[:2]
    pattern = vat_patterns.get(country_code)

    if pattern and re.match(pattern, sanitized_vat_number[2:]):
        return sanitized_vat_number

    return None


def main() -> None:
    """CLI entry point for bulk VAT number processing with VIES API."""
    # Create a CLI argument parser and parse the args
    parser = argparse.ArgumentParser(
        prog="vies-scraper",
        description="Bulk extract VAT data from VIES REST API.",
        epilog="See https://viesapi.eu/ for more information on VIES API usage.",
    )
    parser.add_argument(
        "input",
        nargs="?",
        metavar="FILE",
        type=argparse.FileType("r"),
        default=sys.stdin,
        help="input file that contains line delimited VAT numbers. Defaults to STDIN.",
    )
    parser.add_argument(
        "--output",
        "-o",
        nargs="?",
        metavar="FILE",
        type=argparse.FileType("w"),
        default=sys.stdout,
        help="output CSV file to write the results to. Defaults to STDOUT",
    )
    parser.add_argument(
        "--batch",
        "-b",
        metavar="SIZE",
        type=int,
        default=None,
        help="batch size for processing multiple VAT numbers",
    )
    parser.add_argument(
        "--api",
        default="https://viesapi.eu/api",
        metavar="URL",
        help="VIES API url. Defaults to https://viesapi.eu/api",
    )
    parser.add_argument(
        "--username",
        "-u",
        required=True,
        metavar="USERNAME",
        help="username to log in to https://viesapi.eu/api",
    )
    parser.add_argument(
        "--password",
        "-p",
        required=True,
        metavar="PASSWORD",
        help="password to log in to https://viesapi.eu/api",
    )
    args = parser.parse_args()

    # Extract the list of VAT numbers from the input file, ignoring invalid ones
    vat_numbers = (
        sanitized_vat_number
        for line in args.input
        if (sanitized_vat_number := parse_vat_number(line.strip()))
    )
    args.output.writelines(f"{number}\n" for number in vat_numbers)


if __name__ == "__main__":
    main()
