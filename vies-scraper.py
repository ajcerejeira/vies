#!/usr/bin/env python3

import json
from base64 import b64encode
from typing import Iterable, TypeAlias
from urllib.request import Request

JSON: TypeAlias = None | bool | int | float | str | list["JSON"] | dict[str, "JSON"]
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
