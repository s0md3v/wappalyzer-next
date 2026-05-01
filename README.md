# Wappalyzer Next

This project is a command line tool and python library that uses the [Wappalyzer](https://www.wappalyzer.com/) browser extension and its fingerprints to detect technologies. Other projects that emerged after the discontinuation of the official open-source project are using outdated fingerprints and lack accuracy on dynamic web apps. This project bypasses those limitations by running the extension in Chromium through Playwright.

![demo](https://github.com/user-attachments/assets/7a51b034-c9a7-44e6-aa80-2f8a23311e72)

- [Installation](https://github.com/s0md3v/wappalyzer-next?tab=readme-ov-file#installation)
- [For Users](https://github.com/s0md3v/wappalyzer-next?tab=readme-ov-file#for-users)
- [For Developers](https://github.com/s0md3v/wappalyzer-next?tab=readme-ov-file#for-developers)
- [FAQ](https://github.com/s0md3v/wappalyzer-next?tab=readme-ov-file#faq)

## Installation

After installing the Python package, install Playwright's Chromium browser:

```bash
python -m playwright install chromium
```

In minimal Linux containers, install Chromium's system dependencies as well:

```bash
python -m playwright install-deps chromium
```


#### Install as a command-line tool
```bash
pipx install wappalyzer
pipx run --spec playwright playwright install chromium
```

#### Install as a library
To use it as a library, install it with `pip` inside an isolated container e.g. `venv` or `docker`. You may also `--break-system-packages` to do a 'regular' install but it is not recommended.

```bash
pip install wappalyzer
python -m playwright install chromium
```

#### Install with docker
<details><summary>Steps</summary>

1. Clone the repository:
```bash
git clone https://github.com/s0md3v/wappalyzer-next.git
cd wappalyzer-next
```

2. Build and run with Docker Compose:
```bash
docker compose build
```

3. To scan URLs using the Docker container:

- Scan a single URL:
```bash
docker compose run --rm wappalyzer -i https://example.com
```
- Scan multiple URLs from a file:
```bash
docker compose run --rm wappalyzer -i urls.txt -w 3 -oJ output.json
```
</details>

## For Users
Some common usage examples are given below, refer to list of all options for more information.

- Scan a single URL: `wappalyzer -i https://example.com`
- Scan multiple URLs from a file: `wappalyzer -i urls.txt -w 3`
- Set page-load timeout for full scans: `wappalyzer -i urls.txt -t 15`
- Scan with authentication: `wappalyzer -i https://example.com -c "sessionid=abc123; token=xyz789"`
- Export results to JSON: `wappalyzer -i https://example.com -oJ results.json`
- Export JSON to stdout: `wappalyzer -i https://example.com -oJ`

When an output flag is used without a file, the report is written to stdout. Status lines, banner text, and errors are written to stderr.

#### Options

> Note: For accuracy use 'full' scan type (default). 'fast' and 'balanced' do not use browser emulation.

- `-i`: Input URL or file containing URLs (one per line)
- `--scan-type`: Scan type (default: 'full')
  - `fast`: Quick HTTP-based scan (sends 1 request)
  - `balanced`: HTTP-based scan with more requests
  - `full`: Complete scan using wappalyzer extension
- `-w, --workers`: Number of concurrent workers (default: 5; full scans are capped at 3)
- `-t, --timeout`: Maximum seconds to wait for a page load in full scans (default: 30)
- `-oJ [file]`: JSON output file path, or stdout when the file is omitted or set to `-`
- `-oC [file]`: CSV output file path, or stdout when the file is omitted or set to `-`
- `-oH [file]`: HTML output file path, or stdout when the file is omitted or set to `-`
- `-c, --cookie`: Cookie header string for authenticated scans

## For Developers

The python library is available on pypi as `wappalyzer` and can be imported with the same name.

#### Using the Library

Use `Wappalyzer` when scanning more than one URL. The browser is started once, reused, and closed when the `with` block exits.

```python
from wappalyzer import Wappalyzer

with Wappalyzer(workers=3, timeout=30) as scanner:
    results = scanner.analyze_many([
        'https://example.com',
        'https://github.com',
        'https://python.org',
    ])

for url, technologies in results.items():
    print(url)
    for name, data in technologies.items():
        version = f" {data['version']}" if data['version'] else ""
        print(f"  {name}{version}")
```

The same scanner can also scan one URL at a time without reopening Chromium:

```python
from wappalyzer import Wappalyzer

with Wappalyzer(workers=3, timeout=30) as scanner:
    github = scanner.analyze('https://github.com')
    python = scanner.analyze('https://python.org')
```

For a single URL, `analyze()` is shorter. It creates its own scanner, runs one scan, and closes it.

```python
from wappalyzer import analyze

results = analyze(
    url='https://example.com',
    scan_type='full',  # 'fast', 'balanced', or 'full'
    cookie='sessionid=abc123',
    timeout=30
)
```

Do not call the top-level `analyze()` function in a loop for large jobs. Use `Wappalyzer.analyze_many()` or `Wappalyzer.analyze()` on a reused scanner so Chromium and the Wappalyzer extension are not reloaded for every URL.

#### analyze() Function Parameters

- `url` (str): The URL to analyze
- `scan_type` (str, optional): Type of scan to perform
  - `'fast'`: Quick HTTP-based scan
  - `'balanced'`: HTTP-based scan with more requests
  - `'full'`: Complete scan including JavaScript execution (default)
- `workers` (int, optional): Number of browser workers to create for full scans (default: 1)
- `cookie` (str, optional): Cookie header string for authenticated scans
- `timeout` (int, optional): Maximum seconds to wait for a page load in full scans (default: 30)

#### Return Value

Returns a dictionary with the URL as key and detected technologies as value:

```json
{
  "https://github.com": {
    "Amazon S3": {
      "version": "",
      "confidence": 100,
      "categories": ["CDN"],
      "groups": ["Servers"]
    },
    "React Router": {
      "version": "6",
      "confidence": 100,
      "categories": ["JavaScript frameworks"],
      "groups": ["Web development"]
    }
  },
  "https://example.com": {}
}
```

### FAQ

#### Why Chromium and Playwright?
The full scanner runs the Wappalyzer extension in Chromium through Playwright. Chromium extension support in Playwright is direct and does not require geckodriver or Selenium.

#### What is the difference between 'fast', 'balanced', and 'full' scan types?
- **fast**: Sends a single HTTP request to the URL. Doesn't use the extension.
- **balanced**: Sends additional HTTP requests to .js files, /robots.txt and does DNS queries. Doesn't use the extension.
- **full**: Uses the official Wappalyzer extension to scan the URL in a headless browser.
