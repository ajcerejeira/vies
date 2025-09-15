# vies-scraper

Validate European VAT numbers using the official European Commission's
[VIES (VAT Information Exchange System) service](https://ec.europa.eu/taxation_customs/vies/).

This tool performs batch validation of VAT numbers using the VIES REST API with 
crapy for concurrent processing.

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
./vies.py [FILE] [options]

Arguments:
  FILE                  input file that contains line delimited VAT numbers (defaults to STDIN)

Options:
  -o, --output FILE     output CSV file to write the results to (default: 'vat-numbers.csv')
  -h, --help            show this help message and exit
```

## Examples

### Validate from file

Create a file with VAT numbers (one per line):

```bash
$ cat > vat_numbers.txt << EOF
DE123456789
FR12345678901
ES12345678Z
EOF

$ ./vies.py vat_numbers.txt
```

This will create a CSV file `vat-numbers.csv` with the validation results.

### Validate from stdin

```bash
$ echo -e "DE123456789\nFR12345678901" | ./vies.py
```

### Custom output file

```bash
$ ./vies.py --output results.csv vat_numbers.txt
```

### Expected CSV output format

The output CSV file contains the following columns:

- `countryCode`: The 2-letter country code (e.g., "DE", "FR")
- `vatNumber`: The VAT number without country code
- `valid`: Boolean indicating if the VAT number is valid
- `name`: Company name (if valid and available)
- `address`: Company address (if valid and available)
- `errors`: Any error messages from the validation process

## License

Licensed under the
[GNU Affero General Public License](https://www.gnu.org/licenses/agpl.html).
See [LICENSE](LICENSE) file for more information.
