#!/usr/bin/env python3

import json
from base64 import b64encode
from typing import TypeAlias
from urllib.request import Request

JSON: TypeAlias = None | bool | int | float | str | list["JSON"] | dict[str, "JSON"]
"""Type alias for `json` serializable values."""


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
