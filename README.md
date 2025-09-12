# vies-scraper

Validate European VAT numbers using the official European Commission's 
[VIES (VAT Information Exchange System) service](https://ec.europa.eu/taxation_customs/vies/).

[![GitHub License](https://img.shields.io/github/license/ajcerejeira/vies-scraper)](LICENSE)
[![CI](https://github.com/ajcerejeira/vies-scraper/actions/workflows/ci.yml/badge.svg)](https://github.com/ajcerejeira/vies-scraper/actions/workflows/ci.yml)

## Installation

This is a single Python script that requires
[Python>=3.13](https://www.python.org/downloads/release/python-313/) and uses
[uv](https://docs.astral.sh/uv/) for dependency management.

Download it with [curl](https://curl.se/) and run it:

```bash
curl -O https://raw.githubusercontent.com/ajcerejeira/vies-scraper/main/vies.py
chmod +x vies.py
```

## Usage

```bash
./vies.py check VAT_NUMBER [VAT_NUMBER ...] [options]

Options:
  -f, --format FORMAT   output format for validation results (default: json)
  -o, --output FILE     output file for results (default: <stdout>)
  -h, --help            show this help message and exit
```

### Examples

#### Validate single VAT number (JSON output to stdout)

```bash
$ ./vies.py check DE123456789
{"country_code": "DE", "vat_number": "123456789", "is_valid": true, "request_date": "2024-01-15", "name": "EXAMPLE COMPANY GMBH", "address": "EXAMPLE ADDRESS, 12345 BERLIN"}
```

#### Output as CSV

```bash
$ ./vies.py check --format csv DE123456789
country_code,vat_number,is_valid,request_date,name,address
DE,123456789,True,2024-01-15,EXAMPLE COMPANY GMBH,"EXAMPLE ADDRESS, 12345 BERLIN"
```

## License

Licensed under the
[GNU Affero General Public License](https://www.gnu.org/licenses/agpl.html).
See [LICENSE](LICENSE) file for more information.
