# vies-scraper

Validate European VAT numbers using the official European Commission's 
[VIES (VAT Information Exchange System) service](https://ec.europa.eu/taxation_customs/vies/).

Supports both individual validation via SOAP API and batch validation via REST API.

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

### Individual validation

```bash
./vies.py check VAT_NUMBER [VAT_NUMBER ...] [options]

Options:
  -f, --format FORMAT   output format for validation results (default: json)
  -o, --output FILE     output file for results (default: <stdout>)
  -h, --help            show this help message and exit
```

### Batch validation

```bash
./vies.py batch [FILE] [options]

Options:
  -f, --format FORMAT   output format for validation results (default: json)
  -o, --output FILE     output file to write the results to (default: <stdout>)
  -s, --size SIZE       batch size for processing multiple VAT numbers (default: 99)
  -r, --retries NUMBER  number of retry attempts for failed requests (default: 3)
  -d, --delay SECONDS   delay in seconds between batch API calls (default: 5.0)
  -h, --help            show this help message and exit
```

## Examples

### Individual validation

#### Validate single VAT number (JSON output to stdout)

```bash
$ ./vies.py check DE123456789 | jq
{
  "country_code": "DE",
  "vat_number": "123456789",
  "is_valid": true,
  "name": "EXAMPLE COMPANY GMBH",
  "address": "EXAMPLE ADDRESS, 12345 BERLIN"
}
```

#### Validate multiple VAT numbers

```bash
$ ./vies.py check DE123456789 FR12345678901 ES12345678Z
```

#### Output as CSV

```bash
$ ./vies.py check --format csv DE123456789
country_code,vat_number,is_valid,name,address
DE,123456789,True,EXAMPLE COMPANY GMBH,"EXAMPLE ADDRESS, 12345 BERLIN"
```

#### Save to file

```bash
$ ./vies.py check --format json --output results.json DE123456789
$ ./vies.py check --format csv --output results.csv DE123456789
```

### Batch validation

#### Batch validate from file (line-delimited VAT numbers)

```bash
$ ./vies.py batch input.txt
```

#### Batch validate with custom settings

```bash
$ ./vies.py batch --size 50 --delay 2.0 --format csv --output results.csv input.txt
```

#### Batch validate from stdin

```bash
$ echo -e "DE123456789\nFR12345678901" | ./vies.py batch
```

## License

Licensed under the
[GNU Affero General Public License](https://www.gnu.org/licenses/agpl.html).
See [LICENSE](LICENSE) file for more information.
