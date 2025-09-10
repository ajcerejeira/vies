#!/usr/bin/env python3

import argparse
import csv
import json
import re
import sys
import time
from base64 import b64encode
from collections import deque
from functools import partial, wraps
from itertools import batched, repeat
from io import StringIO
from typing import Callable, Generator, Iterable, Iterator
from urllib.error import URLError
from urllib.request import Request, urlopen
from urllib.response import addinfourl as Response


type JSON = None | bool | int | float | str | list[JSON] | dict[str, JSON]
"""Type alias for `json` serializable values."""


def flatten(
    data: JSON,
    *,
    delimiter: str = ".",
    prefix: str = "",
) -> Generator[tuple[str, None | bool | int | float | str]]:
    """Flatten nested JSON object into key-value pairs with delimiter-separated keys.

    Args:
        data: JSON-serializable data structure to flatten (`dict`, `list`, or scalar).
        delimiter: String used to separate nested keys.
        prefix: Internal parameter for recursion, specifies key prefix.

    Yields:
        Key-value pairs where keys are delimiter-separated paths to leaf values,

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
        >>> dict(flatten(data))                 # doctest: +ELLIPSIS
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


def serialize(file: StringIO, data: Iterable[JSON]) -> None:
    """Serialize JSON data to CSV format with flattened nested structures.

    Converts an iterable of JSON objects into CSV format by flattening nested
    structures using dot notation for keys.
    The CSV fieldnames are determined from the first data item.
    Missing keys in subsequent items are filled with None values, and extra keys
    are ignored.

    Args:
        file: Text stream to write CSV output to.
        data: Iterable of JSON-serializable objects to convert to CSV.

    Examples:
        Basic usage with simple objects::

            >>> from io import StringIO
            >>> output = StringIO()
            >>> data = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
            >>> serialize(output, data)
            >>> print(output.getvalue())        # doctest: +NORMALIZE_WHITESPACE
            name,age
            Alice,30
            Bob,25

        Nested objects are flattened with dot notation::

            >>> output = StringIO()
            >>> data = [
            ...     {"user": {"name": "Alice", "profile": {"city": "NYC"}}},
            ...     {"user": {"name": "Bob", "profile": {"city": "LA"}}}
            ... ]
            >>> serialize(output, data)
            >>> print(output.getvalue())        # doctest: +NORMALIZE_WHITESPACE
            user.name,user.profile.city
            Alice,NYC
            Bob,LA

        Missing keys in subsequent items are handled gracefully::

            >>> output = StringIO()
            >>> data = [
            ...     {"name": "Alice", "email": "alice@example.com"},
            ...     {"name": "Bob"}  # missing email
            ... ]
            >>> serialize(output, data)
            >>> print(output.getvalue())        # doctest: +NORMALIZE_WHITESPACE
            name,email
            Alice,alice@example.com
            Bob,

    """
    rows = (dict(flatten(item)) for item in data)
    first = next(rows, None)
    if not first:
        return

    writer = csv.DictWriter(file, first.keys(), extrasaction="ignore", restval=None)
    writer.writeheader()
    writer.writerow(first)
    writer.writerows(rows)


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
        >>> req.headers["Authorization"]        # doctest: +ELLIPSIS
        'Basic ...'

        Create a POST request with JSON data::

        >>> req = request(
        ...     "/batch/vies",
        ...     body={"batch": {"numbers": ["FI23064613", "SI51510847"]}},
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


type ResponseParser[T] = Callable[[Response], ResponseParserResult[T]]
"""Type alias for response parsers that yield data items or follow requests."""

type ResponseParserResult[T] = Iterator[T | tuple[Request, ResponseParser[T]]]
"""Type alias for `ResponseParser` return values."""

type Crawler[T] = Callable[[Iterable[tuple[Request, ResponseParser[T]]]], Iterator[T]]
"""Type alias for crawler functions that process request-parser pairs."""


def crawl[T](
    requests: Iterable[tuple[Request, ResponseParser[T]]],
    *,
    timeout: float = 30.0,
    retries: int = 1,
    delay: float = 1.0,
    backoff: float = 2.0,
) -> Generator[T]:
    """Breadth-first web crawler with automatic retry logic.

    Executes HTTP requests using a breadth-first queue approach, where each
    response parser can yield data items or additional requests to follow.
    Failed requests are automatically retried with exponential backoff.

    Args:
        requests: Initial collection of (request, parser) tuples to process.
        timeout: HTTP request timeout in seconds.
        retries: Number of retry attempts for failed requests.
        delay: Initial delay between retries in seconds.
        backoff: Multiplier applied to delay after each failed attempt.

    Yields:
        Data items extracted by the response parsers.

    Examples:
        Simple crawling with a basic parser::

            >>> import json
            >>> from urllib.request import Request
            >>>
            >>> # Simple parse function that reads a JSON response and extracts a key
            >>> parse = lambda response: (yield json.loads(response.read()).get("name"))
            >>> requests = [
            ...     (Request("https://jsonplaceholder.typicode.com/users/1"), parse),
            ...     (Request("https://jsonplaceholder.typicode.com/users/2"), parse),
            ...     (Request("https://jsonplaceholder.typicode.com/users/3"), parse)
            ... ]
            >>> results = crawl(requests)
            >>> list(results)
            ['Leanne Graham', 'Ervin Howell', 'Clementine Bauch']

        Crawling with follow-up requests::

            >>> import json
            >>> from urllib.request import Request
            >>>
            >>> def parse_user_detail(response):
            ...     yield json.loads(response.read()).get("name")
            >>>
            >>> def parse_user_list(response):
            ...     data = json.loads(response.read())
            ...     for key in data:
            ...         url = f"https://jsonplaceholder.typicode.com/users/{key['id']}"
            ...         yield (Request(url), parse_user_detail)
            >>>
            >>> initial = Request("https://jsonplaceholder.typicode.com//users")
            >>> results = crawl([(initial, parse_user_list)])
            >>> list(results)                   # doctest: +ELLIPSIS
            ['Leanne Graham', 'Ervin Howell', 'Clementine Bauch', ...]

    """

    @retry((URLError,), retries=retries, delay=delay, backoff=backoff)
    def fetch(request: Request, parse: ResponseParser[T]) -> ResponseParserResult[T]:
        with urlopen(request, timeout=timeout) as response:
            yield from parse(response)

    queue = deque(requests)
    while queue:
        request, parse = queue.popleft()
        for result in fetch(request, parse):
            if isinstance(result, tuple):
                queue.append(result)
            else:
                yield result


def scrape(
    vat_numbers: Iterable[str],
    *,
    crawl: Crawler[JSON],
    factory: RequestFactory,
    batch: int | None = None,
) -> Iterable[JSON]:
    """Scrape VAT information from VIES API using single requests or batch processing.

    Processes VAT numbers through the VIES API using either individual requests
    for immediate results or batch requests for bulk processing. Batch mode uses
    an asynchronous submit-then-poll pattern for handling multiple VAT numbers.

    Args:
        vat_numbers: Iterable of VAT numbers to process.
        crawl: Crawler function to process request-parser pairs.
        factory: Request factory function to create HTTP requests.
        batch: Optional batch size for bulk processing.

    Yields:
        JSON data containing VAT validation results for each processed number.

    Examples:
        Single VAT number processing::

            >>> from functools import partial
            >>>
            >>> factory = partial(
            ...     request,
            ...     base_url="https://viesapi.eu/api-test",
            ...     username="test_id",
            ...     password="test_key"
            ... )
            >>> vat_numbers = ["PT501613897"]
            >>> results = scrape(vat_numbers, crawl=crawl, factory=factory)
            >>> list(results)                   # doctest: +ELLIPSIS
            [{..., 'countryCode': 'PT', 'vatNumber': '501613897', ...}]

    """

    def parse_get_vies_data_parsed(response: Response) -> ResponseParserResult[JSON]:
        """Parse single VAT number response from GET /get/vies/parsed/euvat/{number}."""
        body = json.loads(response.read())["vies"]
        yield body

    def parse_post_vies_data_batch(response: Response) -> ResponseParserResult[JSON]:
        """Parse batch response from POST /batch/vies and yield follow up request."""
        body = json.loads(response.read())
        token = body["batch"]["token"]
        yield (factory(f"/batch/vies/{token}"), parse_get_vies_data_batch)

    def parse_get_vies_data_batch(response: Response) -> ResponseParserResult[JSON]:
        """Parse batch results response from GET /batch/vies/{token}."""
        body = json.loads(response.read())
        if "error" in body:
            raise URLError(body["error"]["description"])
        yield from body["batch"]["numbers"]

    if batch:
        requests = (
            factory("/batch/vies", {"batch": {"numbers": list(chunk)}})
            for chunk in batched(vat_numbers, batch)
        )
        parse = parse_post_vies_data_batch
    else:
        requests = (
            factory(f"/get/vies/parsed/euvat/{vat_number}")
            for vat_number in vat_numbers
        )
        parse = parse_get_vies_data_parsed
    return crawl(zip(requests, repeat(parse)))


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

    # Scrape all the VAT numbers
    results = scrape(
        vat_numbers,
        crawl=crawl,
        factory=partial(
            request,
            base_url=args.api,
            username=args.username,
            password=args.password,
        ),
        batch=args.batch,
    )

    # Write the fetched results to the CSV file
    serialize(args.output, results)


if __name__ == "__main__":
    main()
