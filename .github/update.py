import json
import re
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from textwrap import dedent


URL = "https://addons.mozilla.org/firefox/downloads/latest/wappalyzer/platform:2/wappalyzer.xpi"
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "wappalyzer" / "data"

PROMPT_BLOCK = re.compile(
    r"^[ \t]*const current = await get(?:Cached)?Option\('version'\)\n"
    r".*?"
    r"(?=^[ \t]*initDone\(\))",
    re.MULTILINE | re.DOTALL,
)

PERSIST_HOSTNAMES = re.compile(
    r"(?P<indent>^[ \t]*)async persistHostnames\(\) \{\n"
    r".*?"
    r"^(?P=indent)\},\n",
    re.MULTILINE | re.DOTALL,
)

LEGACY_HOSTNAMES = re.compile(
    r"(?P<indent>^[ \t]*)await setOption\(\n"
    r"(?P=indent)  'hostnames',\n"
    r".*?"
    r"^(?P=indent)\)\n",
    re.MULTILINE | re.DOTALL,
)


def indent(text, prefix):
    lines = dedent(text).strip("\n").splitlines()
    return "\n".join(f"{prefix}{line}" if line else "" for line in lines) + "\n"


def patch_index_js(content):
    content = PROMPT_BLOCK.sub("", content, count=1)

    content, persist_count = PERSIST_HOSTNAMES.subn(
        lambda match: indent(
            """
            async persistHostnames() {
              Driver.pruneHostnamesCache()

              const hostnames = {}

              for (const hostname of Object.keys(Driver.cache.hostnames)) {
                const cache = Driver.cache.hostnames[hostname]

                hostnames[hostname] = {
                  ...cache,
                  detections: cache.detections
                    .filter(({ technology }) => technology)
                    .map(
                      ({
                        technology: { name: technology },
                        pattern: { regex, confidence },
                        version,
                        rootPath,
                        lastUrl,
                      }) => ({
                        technology,
                        pattern: {
                          regex: regex.source,
                          confidence,
                        },
                        version,
                        rootPath,
                        lastUrl,
                      })
                    ),
                }
              }

              browser.tabs.create({
                url: JSON.stringify(hostnames),
              })
            },
            """,
            match.group("indent"),
        ),
        content,
        count=1,
    )

    if not persist_count:
        content, legacy_count = LEGACY_HOSTNAMES.subn(
            lambda match: indent(
                """
                browser.tabs.create({
                  url: JSON.stringify(
                    Object.keys(Driver.cache.hostnames).reduce(
                      (hostnames, hostname) => ({
                        ...hostnames,
                        [hostname]: {
                          ...cache,
                          detections: Driver.cache.hostnames[hostname].detections
                            .filter(({ technology }) => technology)
                            .map(
                              ({
                                technology: { name: technology },
                                pattern: { regex, confidence },
                                version,
                                rootPath,
                                lastUrl,
                              }) => ({
                                technology,
                                pattern: {
                                  regex: regex.source,
                                  confidence,
                                },
                                version,
                                rootPath,
                                lastUrl,
                              })
                            ),
                        },
                      }),
                      {}
                    )
                  ),
                })
                """,
                match.group("indent"),
            ),
            content,
            count=1,
        )

        if not legacy_count:
            raise RuntimeError("Failed to patch js/index.js")

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
