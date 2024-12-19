# Wappalyzer.Next

This is [Wappalyzer](https://www.wappalyzer.com/) browser extenstion but as a command line tool and python library. Unlike other projects emerged after the official open source project, this one uses the official extension for accurate results.

If you wish to use it as a tool, see the "For Users" section.
To use it a python library, see the "For Developers" section.

## For Users
### Installation

```bash
pipx install wappalyzer
```

### Command Line Usage

Basic usage:

```bash
wappalyzer -i <url_or_file> [options]
```

### Examples

Scan a single URL:
```bash
wappalyzer -i https://example.com
```

Scan multiple URLs from a file:
```bash
wappalyzer -i urls.txt -t 10
```

Scan with authentication:
```bash
wappalyzer -i https://example.com -c "sessionid=abc123; token=xyz789"
```

Export results to JSON:
```bash
wappalyzer -i https://example.com -oJ results.json
```

### Options

> Note: For accuracy use 'full' scan type. 'fast' and 'balanced' do not use browser emulation.

- `-i`: Input URL or file containing URLs (one per line)
- `--scan-type`: Scan type (default: 'full')
  - `fast`: Quick HTTP-based scan (sends 1 request)
  - `balanced`: HTTP-based scan with more requests
  - `full`: Complete scan using wappalyzer extension
- `-t, --threads`: Number of concurrent threads (default: 5)
- `-oJ`: JSON output file path
- `-oC`: CSV output file path
- `-c, --cookie`: Cookie string for authenticated scans

## For Developers

The python library is a available on pypi as `wappalyzer`.

### Using the Library

The main function you'll interact with is `analyze()`:

```python
from wappalyzer import analyze

# Basic usage
results = analyze('https://example.com')

# With options
results = analyze(
    url='https://example.com',
    scan_type='full',  # 'fast', 'balanced', or 'full'
    threads=3,
    cookie='sessionid=abc123'
)
```

#### analyze() Function Parameters

- `url` (str): The URL to analyze
- `scan_type` (str, optional): Type of scan to perform
  - `'fast'`: Quick HTTP-based scan
  - `'balanced'`: HTTP-based scan with more requests
  - `'full'`: Complete scan including JavaScript execution (default)
- `threads` (int, optional): Number of threads for parallel processing (default: 3)
- `cookie` (str, optional): Cookie string for authenticated scans

#### Return Value

Returns a dictionary with the URL as key and detected technologies as value:

```json
{
  "https://github.com": {
    "Amazon S3": {"version": "", "confidence": 100, "categories": ["CDN"], "groups": ["Servers"]},
    "lit-html": {"version": "1.1.2", "confidence": 100, "categories": ["JavaScript libraries"], "groups": ["Web development"]},
    "React Router": {"version": "6", "confidence": 100, "categories": ["JavaScript frameworks"], "groups": ["Web development"]},
  "https://google.com" : {},
  "https://example.com" : {},
}
```

### FAQ

#### Why use Firefox instead of Chrome?
Firefox extensions are .xpi files which are essentially zip files. This makes it easier to extract data and slightly modify the extension to make this tool work.

#### What is the difference between 'fast', 'balanced', and 'full' scan types?
- 'fast': Sends a single HTTP request to the URL
- 'balanced': Sends additional HTTP requests to .js files, /robots.txt annd does DNS queries
- 'full': Uses the official Wappalyzer extension to scan the URL in a headless browser
