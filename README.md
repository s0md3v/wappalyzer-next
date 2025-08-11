# Wappalyzer Next

This project is a command line tool and python library that uses [Wappalyzer](https://www.wappalyzer.com/) extension (and its fingerprints) to detect technologies. Other projects that emerged after the discontinuation of the official open-source project are using outdated fingerprints and lack accuracy when used on dynamic web apps. This project bypasses those limitations.

![demo](https://github.com/user-attachments/assets/7a51b034-c9a7-44e6-aa80-2f8a23311e72)

- [Installation](https://github.com/s0md3v/wappalyzer-next?tab=readme-ov-file#installation)
- [For Users](https://github.com/s0md3v/wappalyzer-next?tab=readme-ov-file#for-users)
- [For Developers](https://github.com/s0md3v/wappalyzer-next?tab=readme-ov-file#for-developers)
- [FAQ](https://github.com/s0md3v/wappalyzer-next?tab=readme-ov-file#faq)

## Installation

Before installing wappalyzer, you will need to install [Firefox](https://www.mozilla.org/en-US/firefox/windows/) and [geckodriver](https://github.com/mozilla/geckodriver/releases). Below are detailed steps for setting up geckodriver but you may use google/youtube for help.
<details>
<summary>Setting up geckodriver</summary>

### Step 1: Download GeckoDriver
1. Visit the official GeckoDriver releases page on GitHub:  
   [https://github.com/mozilla/geckodriver/releases](https://github.com/mozilla/geckodriver/releases)
2. Download the version compatible with your system:
   - For Windows: `geckodriver-vX.XX.X-win64.zip`
   - For macOS: `geckodriver-vX.XX.X-macos.tar.gz`
   - For Linux: `geckodriver-vX.XX.X-linux64.tar.gz`
3. Extract the downloaded file to a folder of your choice.

### Step 2: Add GeckoDriver to the System Path
To ensure Selenium can locate the GeckoDriver executable:
- **Windows**:
  1. Move the `geckodriver.exe` to a directory (e.g., `C:\WebDrivers\`).
  2. Add this directory to the system's PATH:
     - Open **Environment Variables**.
     - Under **System Variables**, find and select the `Path` variable, then click **Edit**.
     - Click **New** and enter the directory path where `geckodriver.exe` is stored.
     - Click **OK** to save.
- **macOS/Linux**:
  1. Move the `geckodriver` file to `/usr/local/bin/` or another directory in your PATH.
  2. Use the following command in the terminal:
     ```bash
     sudo mv geckodriver /usr/local/bin/
     ```
     Ensure `/usr/local/bin/` is in your PATH.
</details>


#### Install as a command-line tool
```bash
pipx install wappalyzer
```

#### Install as a library
To use it as a library, install it with `pip` inside an isolated container e.g. `venv` or `docker`. You may also `--break-system-packages` to do a 'regular' install but it is not recommended.

#### Install with docker
<details><summary>Steps</summary>

1. Clone the repository:
```bash
git clone https://github.com/s0md3v/wappalyzer-next.git
cd wappalyzer-next
```

2. Build and run with Docker Compose:
```bash
docker compose up -d
```

3. To scan URLs using the Docker container:

- Scan a single URL:
```bash
docker compose run --rm wappalyzer -i https://example.com
```
- Scan Multiple URLs from a file:
```bash
docker compose run --rm wappalyzer -i https://example.com -oJ output.json
```
</details>

## For Users
Some common usage examples are given below, refer to list of all options for more information.

- Scan a single URL:
`wappalyzer -i https://example.com`
- Scan multiple URLs from a file: `wappalyzer -i urls.txt -t 10`
- Scan with authentication: `wappalyzer -i https://example.com -c "sessionid=abc123; token=xyz789"`
- Export results to JSON: `wappalyzer -i https://example.com -oJ results.json`

#### Options

> Note: For accuracy use 'full' scan type (default). 'fast' and 'balanced' do not use browser emulation.

- `-i`: Input URL or file containing URLs (one per line)
- `--scan-type`: Scan type (default: 'full')
  - `fast`: Quick HTTP-based scan (sends 1 request)
  - `balanced`: HTTP-based scan with more requests
  - `full`: Complete scan using wappalyzer extension
- `-t, --threads`: Number of concurrent threads (default: 5)
- `-oJ`: JSON output file path
- `-oC`: CSV output file path
- `-oH`: HTML output file path
- `-c, --cookie`: Cookie header string for authenticated scans

## For Developers

The python library is available on pypi as `wappalyzer` and can be imported with the same name.

#### Using the Library

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
- `cookie` (str, optional): Cookie header string for authenticated scans

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
}}
```

### FAQ

#### Why use Firefox instead of Chrome?
Firefox extensions are .xpi files which are essentially zip files. This makes it easier to extract data and slightly modify the extension to make this tool work.

#### What is the difference between 'fast', 'balanced', and 'full' scan types?
- **fast**: Sends a single HTTP request to the URL. Doesn't use the extension.
- **balanced**: Sends additional HTTP requests to .js files, /robots.txt and does DNS queries. Doesn't use the extension.
- **full**: Uses the official Wappalyzer extension to scan the URL in a headless browser.
