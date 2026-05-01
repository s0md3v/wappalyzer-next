import json
import re
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path


URL = "https://addons.mozilla.org/firefox/downloads/latest/wappalyzer/platform:2/wappalyzer.xpi"
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "wappalyzer" / "data"

PROMPT_BLOCK = re.compile(
    r"^[ \t]*const current = await get(?:Cached)?Option\('version'\)\n"
    r".*?"
    r"(?=^[ \t]*initDone\(\))",
    re.MULTILINE | re.DOTALL,
)


def patch_index_js(content):
    content = PROMPT_BLOCK.sub("", content, count=1)

    if "https://www.wappalyzer.com/installed/" in content:
        raise RuntimeError("Failed to remove install prompt from js/index.js")

    if "https://www.wappalyzer.com/upgraded/" in content:
        raise RuntimeError("Failed to remove upgrade prompt from js/index.js")

    return content


DATA_DIR.mkdir(parents=True, exist_ok=True)

with tempfile.TemporaryDirectory(prefix="wappalyzer-update-") as tempdir:
    tempdir = Path(tempdir)
    archive_path = tempdir / "wappalyzer.xpi"
    extract_dir = tempdir / "wappalyzer"

    urllib.request.urlretrieve(URL, archive_path)

    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(extract_dir)

    index_path = extract_dir / "js" / "index.js"
    index_path.write_text(
        patch_index_js(index_path.read_text(encoding="utf-8")),
        encoding="utf-8",
    )

    technologies = {}
    for path in sorted((extract_dir / "technologies").glob("*.json")):
        technologies.update(json.loads(path.read_text(encoding="utf-8")))

    (DATA_DIR / "technologies.json").write_text(
        json.dumps(technologies, indent=4) + "\n",
        encoding="utf-8",
    )
    shutil.copy2(extract_dir / "groups.json", DATA_DIR / "groups.json")
    shutil.copy2(extract_dir / "categories.json", DATA_DIR / "categories.json")

    with zipfile.ZipFile(DATA_DIR / "wappalyzer.xpi", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(extract_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(extract_dir))
