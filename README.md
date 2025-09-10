# vies-scraper

Bulk extract VAT information from
[VIES VAT number validation service](https://viesapi.eu/).

[![GitHub License](https://img.shields.io/github/license/ajcerejeira/vies-scraper)](LICENSE)
[![CI](https://github.com/ajcerejeira/vies-scraper/actions/workflows/ci.yml/badge.svg)](https://github.com/ajcerejeira/vies-scraper/actions/workflows/ci.yml)

## Installation

This is a single
[Python>=3.13](https://www.python.org/downloads/release/python-313/).
script with no dependencies.
Download it with [curl](https://curl.se/), mark it as an executable, and run it:


```bash
curl -O https://raw.githubusercontent.com/ajcerejeira/vies-scraper/main/vies.py
chmod +x vies.py
```

## Usage

```bash
./vies.py input.txt --username YOUR_USERNAME --password YOUR_PASSWORD [options]

Options:
  -o, --output FILE     Output CSV file (default: stdout)
  -b, --batch SIZE      Batch size for bulk processing
  --api URL             API endpoint (default: https://viesapi.eu/api)
```

### Example

Try this script with the
[VIES API test environment](https://viesapi.eu/test-vies-api/).
The [examples/test-vat-numbers.txt](examples/test-vat-numbers.txt) file contains
the list of available VAT numbers in the test instance.

```bash
./vies.py examples/test-vat-numbers.txt --output=out.csv    \ 
    --api=https://viesapi.eu/api-test                       \ 
    --username=test_id                                      \ 
    --password=test_key                                     \ 
    --batch=30
```

### Input Format

Text file with one VAT number per line:

```
PT501613897
DE327990207
FR10402571889
```

### Output

CSV with flattened VAT information:

```csv
uid,countryCode,vatNumber,valid,traderName,traderAddress,date
abc123,PT,501613897,True,EXAMPLE COMPANY LDA,EXAMPLE ADDRESS,2024-01-15
```

## License

Licensed under the
[GNU Affero General Public License](https://www.gnu.org/licenses/agpl.html).
See [LICENSE](LICENSE) file for more information.
