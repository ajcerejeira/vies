#!/usr/bin/env python3

# /// script
# dependencies = ["scrapy"]
# ///

"""VIES VAT number validation CLI tool.

This module provides a command-line interface for validating European VAT
numbers using the VIES (VAT Information Exchange System) REST API.
It uses Scrapy to handle concurrent requests and outputs results to a CSV file.
"""

import argparse
import json
import sys
from collections.abc import AsyncIterator, Iterator
from typing import TypedDict

from scrapy import Spider
from scrapy.crawler import CrawlerProcess
from scrapy.http import JsonRequest, JsonResponse, Response


class VIESItem(TypedDict):
    """TypedDict representing a VIES validation result."""

    country_code: str
    vat_number: str
    valid: bool
    name: str | None
    address: str | None
    errors: str | None


class VIESSpider(Spider):
    """Spider to validate European VAT numbers using the VIES API."""

    name = "vies"

    async def start(self) -> AsyncIterator[JsonRequest]:
        """Generate JSON requests for each VAT number to be validated."""
        vat_numbers = getattr(self, "vat_numbers", [])
        url = "https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number"
        for vat_number in vat_numbers:
            data = {"country_code": vat_number[:2], "vat_number": vat_number[2:]}
            yield JsonRequest(
                url,
                method="POST",
                data=data,
                callback=self.parse,
                cb_kwargs={"payload": data},
            )

    def parse(self, response: Response, payload: dict[str, str]) -> Iterator[VIESItem]:
        """Parse VIES API response and handle errors."""
        result = VIESItem(
            country_code=payload["countryCode"],
            vat_number=payload["vatNumber"],
            valid=False,
            name=None,
            address=None,
            errors=None,
        )
        try:
            data = response.json() if isinstance(response, JsonResponse) else {}
            result["valid"] = data.get("valid", False)
            result["name"] = data.get("name", None)
            result["address"] = data.get("address", None)
            if errors := data.get("errorWrappers", None):
                result["errors"] = json.dumps(errors)
        except Exception as error:
            result["errors"] = str(error)
        finally:
            yield result


def main() -> None:
    """Run the VIES CLI tool."""
    # Build the CLI argument parser for the vies app
    parser = argparse.ArgumentParser(
        prog="vies",
        description="Validate European VAT numbers using the VIES service",
        epilog=(
            "For more information about VIES, visit:"
            "https://ec.europa.eu/taxation_customs/vies/"
        ),
    )
    parser.add_argument(
        "input",
        nargs="?",
        metavar="FILE",
        type=argparse.FileType("r"),
        default=sys.stdin,
        help="input file that contains line delimited VAT numbers (defaults to STDIN)",
    )
    parser.add_argument(
        "--output",
        "-o",
        nargs="?",
        metavar="FILE",
        default="vat-numbers.csv",
        help="output CSV file to write the results to (defaults to 'vat-numbers.csv')",
    )
    args = parser.parse_args()

    # Start the scrapy crawler
    process = CrawlerProcess(
        settings={
            "AUTOTHROTTLE_ENABLED": True,
            "CONCURRENT_REQUESTS_PER_DOMAIN": 32,
            "CONCURRENT_REQUESTS_PER_IP": 32,
            "CONCURRENT_REQUESTS": 32,
            "COOKIES_ENABLED": False,
            "DOWNLOAD_DELAY": 0.1,
            "FEEDS": {args.output: {"format": "csv", "overwrite": True}},
            "HTTPCACHE_ENABLED": True,
            "HTTPERROR_ALLOW_ALL": True,
            "JOBDIR": ".scrapy/crawls/",
            "LOG_FILE": "vies.log",
            "RETRY_ENABLED": True,
            "RETRY_HTTP_CODES": [408, 429, 500, 502, 503, 504, 522, 524],
            "RETRY_TIMES": 3,
        }
    )
    process.crawl(VIESSpider, vat_numbers=(line.strip() for line in args.input))
    process.start()


if __name__ == "__main__":
    main()
