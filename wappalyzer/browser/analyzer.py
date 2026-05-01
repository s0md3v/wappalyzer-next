import asyncio
import json
import os
import shutil
import sys
import tempfile
import zipfile
from contextlib import asynccontextmanager
from http.cookies import SimpleCookie
from pathlib import Path

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from wappalyzer.core.config import extension_path
from wappalyzer.core.utils import create_result


WAPPALYZER_POPUP_PATH = "html/popup.html"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
BLOCKED_RESOURCE_TYPES = {"image", "font", "media"}

SELECT_TARGET_TAB_SCRIPT = """
async (targetUrl) => {
  const parseUrl = (value) => {
    try {
      return new URL(value)
    } catch (_) {
      return null
    }
  }

  const queryTabs = () => {
    if (typeof browser !== 'undefined' && browser.tabs?.query) {
      return browser.tabs.query({})
    }

    return new Promise((resolve, reject) => {
      chrome.tabs.query({}, (tabs) => {
        const error = chrome.runtime.lastError

        if (error) {
          reject(new Error(error.message))

          return
        }

        resolve(tabs || [])
      })
    })
  }

  const target = parseUrl(targetUrl)

  if (!target || !/^https?:$/.test(target.protocol)) {
    return null
  }

  const tabs = await queryTabs()
  const isTargetTab = (tab, exact) => {
    if (!tab || !tab.url) {
      return false
    }

    const parsed = parseUrl(tab.url)

    if (!parsed || !/^https?:$/.test(parsed.protocol)) {
      return false
    }

    return exact
      ? parsed.href === target.href
      : parsed.hostname === target.hostname
  }

  return (
    tabs.find((tab) => isTargetTab(tab, true)) ||
    tabs.find((tab) => isTargetTab(tab, false)) ||
    null
  )
}
"""

GET_DETECTIONS_FOR_TAB_SCRIPT = """
async (selectedTab) => {
  const sendMessage = (message) => {
    if (typeof browser !== 'undefined' && browser.runtime?.sendMessage) {
      return browser.runtime
        .sendMessage(message)
        .catch((error) => ({ __error: error.message || String(error) }))
    }

    return new Promise((resolve) => {
      chrome.runtime.sendMessage(message, (response) => {
        const error = chrome.runtime.lastError

        if (error) {
          resolve({ __error: error.message || String(error) })

          return
        }

        resolve(response)
      })
    })
  }

  const normaliseDetection = (detection) => {
    const technology = detection.technology
    const pattern = detection.pattern || {}
    const confidence = Number(
      pattern.confidence ?? detection.confidence
    )
    const technologyName =
      technology && typeof technology === 'object'
        ? technology.name
        : technology || detection.name || detection.slug

    return {
      technology: technologyName,
      pattern: {
        regex: pattern.regex
          ? String(pattern.regex.source || pattern.regex)
          : '',
        confidence: Number.isFinite(confidence) ? confidence : 100,
      },
      version: detection.version || '',
      rootPath: detection.rootPath || '',
      lastUrl: detection.lastUrl || '',
    }
  }

  if (!selectedTab) {
    return []
  }

  const response = await sendMessage({
    source: 'popup.js',
    func: 'getDetectionsForTab',
    args: [{ id: selectedTab.id, url: selectedTab.url }],
  })

  if (response?.__error) {
    return response
  }

  const detections = Array.isArray(response)
    ? response
    : Array.isArray(response?.detections)
      ? response.detections
      : []

  return detections
    .filter(
      (detection) =>
        detection?.technology || detection?.name || detection?.slug
    )
    .map(normaliseDetection)
}
"""

PAGE_ACTIVITY_SCRIPT = """
() => {
  const now = performance.now()

  if (!window.__wappalyzerActivityStarted) {
    window.__wappalyzerActivityStarted = true
    window.__wappalyzerLastMutationAt = now
    window.__wappalyzerMutationCount = 0

    try {
      new MutationObserver(() => {
        window.__wappalyzerLastMutationAt = performance.now()
        window.__wappalyzerMutationCount += 1
      }).observe(document.documentElement, {
        childList: true,
        subtree: true,
        attributes: true,
      })
    } catch (_) {}
  }

  const relevantTypes = new Set(['script', 'fetch', 'xmlhttprequest', 'beacon', 'css'])
  const isRelevantResource = (entry) =>
    relevantTypes.has(entry.initiatorType) ||
    (
      entry.initiatorType === 'link' &&
      /\\.css(?:[?#]|$)/i.test(entry.name || '')
    )
  let relevantCount = 0
  let lastRelevantAt = 0

  try {
    for (const entry of performance.getEntriesByType('resource')) {
      if (!isRelevantResource(entry)) {
        continue
      }

      relevantCount += 1
      lastRelevantAt = Math.max(
        lastRelevantAt,
        entry.responseEnd || entry.startTime || 0
      )
    }
  } catch (_) {}

  return {
    readyState: document.readyState,
    relevantCount,
    lastRelevantAge: lastRelevantAt ? now - lastRelevantAt : null,
    lastMutationAge: window.__wappalyzerLastMutationAt
      ? now - window.__wappalyzerLastMutationAt
      : null,
    mutationCount: window.__wappalyzerMutationCount || 0,
  }
}
"""

STIMULATE_SCRIPT = """
(maxDuration) => {
  if (!window.__wappalyzerStimulusUntil || Date.now() > window.__wappalyzerStimulusUntil) {
    window.__wappalyzerStimulusUntil = Date.now() + maxDuration + 100

    ;(async () => {
      if (maxDuration <= 0) {
        return
      }

      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
      const startedAt = Date.now()
      const height = Math.max(
        document.body?.scrollHeight || 0,
        document.documentElement?.scrollHeight || 0
      )
      const width = Math.max(
        document.documentElement?.clientWidth || window.innerWidth || 1,
        1
      )
      const steps = [0.25, 0.5, 0.75, 1, 0]

      for (const step of steps) {
        const elapsed = Date.now() - startedAt

        if (elapsed >= maxDuration) {
          break
        }

        window.scrollTo(0, Math.max(0, height * step - window.innerHeight))
        document.dispatchEvent(
          new MouseEvent('mousemove', {
            view: window,
            bubbles: true,
            cancelable: true,
            clientX: Math.max(1, Math.floor(width * 0.5)),
            clientY: Math.max(1, Math.floor(window.innerHeight * 0.5)),
          })
        )

        if (document.body?.focus) {
          document.body.focus()
        }

        window.dispatchEvent(new Event('focus'))
        await sleep(Math.min(250, Math.max(0, maxDuration - elapsed)))
      }
    })().catch(() => {})
  }
}
"""


def _validate_extension_dir(extension_dir):
    required_files = (
        "manifest.json",
        "html/popup.html",
        "js/background.js",
        "js/index.js",
        "js/content.js",
    )

    for relative_path in required_files:
        if not (extension_dir / relative_path).is_file():
            raise RuntimeError(f"Missing extension file: {relative_path}")

    manifest = json.loads((extension_dir / "manifest.json").read_text(encoding="utf-8"))
    errors = []

    if manifest.get("manifest_version") != 3:
        errors.append("manifest_version must be 3")

    if manifest.get("action", {}).get("default_popup") != WAPPALYZER_POPUP_PATH:
        errors.append(f"action.default_popup must be {WAPPALYZER_POPUP_PATH}")

    if not manifest.get("background", {}).get("service_worker"):
        errors.append("background.service_worker is required")

    if "scripts" in manifest.get("background", {}):
        errors.append("background.scripts must be absent for Chromium MV3")

    if "browser_specific_settings" in manifest:
        errors.append("browser_specific_settings must be absent")

    if errors:
        raise RuntimeError("Invalid bundled Chromium extension: " + "; ".join(errors))


def _prepare_extension_dir(extension_archive_path):
    extension_dir = Path(tempfile.mkdtemp(prefix="wappalyzer-extension-"))

    with zipfile.ZipFile(extension_archive_path) as archive:
        archive.extractall(extension_dir)

    _validate_extension_dir(extension_dir)

    return extension_dir


def _detection_signature(detections):
    parts = []

    for detection in detections or ():
        technology = detection.get("technology") or detection.get("name") or detection.get("slug")

        if not technology:
            continue

        pattern = detection.get("pattern") or {}
        confidence = pattern.get("confidence", detection.get("confidence", ""))
        parts.append(f"{technology}:{detection.get('version', '')}:{confidence}")

    return "|".join(sorted(parts))


def _activity_signature(activity):
    return ":".join(
        str(activity.get(key, ""))
        for key in ("readyState", "relevantCount", "mutationCount")
    )


def _page_quiet(activity, quiet_ms=1000):
    if activity.get("unavailable"):
        return True

    recent_resource = (
        activity.get("lastRelevantAge") is not None
        and activity["lastRelevantAge"] < quiet_ms
    )
    recent_mutation = (
        activity.get("lastMutationAge") is not None
        and activity["lastMutationAge"] < quiet_ms
    )

    return (
        activity.get("readyState") == "complete"
        and not recent_resource
        and not recent_mutation
    )


class BrowserDriver:
    def __init__(self, context, page, user_data_dir, extension_id, timeout_ms):
        self.context = context
        self.page = page
        self.user_data_dir = Path(user_data_dir)
        self.extension_id = extension_id
        self.timeout_ms = timeout_ms
        self.popup = None
        self.pending_cookies = []

    def add_cookie(self, cookie):
        self.pending_cookies.append(cookie)

    async def apply_pending_cookies(self, url):
        if not self.pending_cookies:
            return

        cookies = []

        for cookie in self.pending_cookies:
            cookies.append({
                "name": cookie["name"],
                "value": cookie["value"],
                "url": url,
            })

        self.pending_cookies = []
        await self.context.add_cookies(cookies)

    async def reset(self):
        try:
            await self.context.clear_cookies()
        except Exception:
            pass

        try:
            await self.page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
        except Exception:
            pass

    async def close(self):
        try:
            await self.context.close()
        except Exception:
            pass

        shutil.rmtree(self.user_data_dir, ignore_errors=True)


class DriverPool:
    def __init__(self, size=3, max_retries=3, timeout=30):
        self.size = size
        self.max_retries = max_retries
        self.timeout = timeout
        self.queue = asyncio.Queue()
        self.closed = False
        self.playwright = None
        self.extension_dir = None
        self.drivers = []

    async def start(self):
        self.playwright = await async_playwright().start()
        self.extension_dir = _prepare_extension_dir(os.path.abspath(extension_path))

        for _ in range(self.size):
            driver = await self._create_driver()

            if driver:
                self.drivers.append(driver)
                await self.queue.put(driver)

        if self.queue.empty():
            raise RuntimeError("Failed to initialize Chromium browser contexts")

    async def grow_to(self, size):
        if self.closed or size <= self.size:
            return

        additional = size - self.size
        self.size = size
        for _ in range(additional):
            driver = await self._create_driver()

            if driver:
                self.drivers.append(driver)
                await self.queue.put(driver)

    async def _create_driver(self):
        for attempt in range(self.max_retries):
            user_data_dir = tempfile.mkdtemp(prefix="wappalyzer-chromium-")
            context = None

            try:
                context = await self.playwright.chromium.launch_persistent_context(
                    user_data_dir,
                    channel="chromium",
                    headless=True,
                    viewport={"width": 1366, "height": 900},
                    user_agent=USER_AGENT,
                    timezone_id="UTC",
                    reduced_motion="reduce",
                    ignore_https_errors=True,
                    args=[
                        f"--disable-extensions-except={self.extension_dir}",
                        f"--load-extension={self.extension_dir}",
                        "--disable-background-networking",
                        "--disable-breakpad",
                        "--disable-client-side-phishing-detection",
                        "--disable-component-update",
                        "--disable-crash-reporter",
                        "--disable-default-apps",
                        "--disable-dev-shm-usage",
                        "--disable-domain-reliability",
                        "--disable-features=Translate,MediaRouter",
                        "--disable-notifications",
                        "--disable-speech-api",
                        "--disable-sync",
                        "--metrics-recording-only",
                        "--mute-audio",
                        "--no-first-run",
                        "--no-default-browser-check",
                    ],
                )

                timeout_ms = self.timeout * 1000
                context.set_default_timeout(timeout_ms)
                context.set_default_navigation_timeout(timeout_ms)

                async def route_handler(route):
                    if route.request.resource_type in BLOCKED_RESOURCE_TYPES:
                        await route.abort()
                    else:
                        await route.continue_()

                await context.route("**/*", route_handler)

                extension_id = await self._get_extension_id(context)
                pages = context.pages
                page = pages[0] if pages else await context.new_page()

                return BrowserDriver(context, page, user_data_dir, extension_id, timeout_ms)
            except Exception as e:
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass

                shutil.rmtree(user_data_dir, ignore_errors=True)
                print(f"Attempt {attempt + 1} failed: {str(e)}", file=sys.stderr)
                await asyncio.sleep(1)

        return None

    async def _get_extension_id(self, context):
        service_workers = context.service_workers
        service_worker = service_workers[0] if service_workers else None

        if service_worker is None:
            service_worker = await context.wait_for_event("serviceworker", timeout=10000)

        return service_worker.url.split("/")[2]

    @asynccontextmanager
    async def get_driver(self):
        driver = await self.queue.get()
        reusable = True

        try:
            yield driver
        except Exception:
            reusable = False
            await driver.close()
            raise
        finally:
            if not reusable:
                return

            if self.closed:
                await driver.close()
            else:
                await driver.reset()
                await self.queue.put(driver)

    async def cleanup(self):
        if self.closed:
            return

        self.closed = True
        drivers = list(self.drivers)
        self.drivers = []

        for driver in drivers:
            await driver.close()

        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception:
                pass

        if self.extension_dir:
            shutil.rmtree(self.extension_dir, ignore_errors=True)


async def _ensure_popup(driver):
    popup_url = f"chrome-extension://{driver.extension_id}/{WAPPALYZER_POPUP_PATH}"

    if driver.popup and not driver.popup.is_closed():
        if driver.popup.url != popup_url:
            await driver.popup.goto(popup_url, wait_until="domcontentloaded")

        return driver.popup

    driver.popup = await driver.context.new_page()
    await driver.popup.goto(popup_url, wait_until="domcontentloaded")

    return driver.popup


async def _stimulate_page(page, max_duration_ms=1250):
    try:
        await page.evaluate(STIMULATE_SCRIPT, max_duration_ms)
    except Exception:
        pass


async def _page_activity(page):
    try:
        return await page.evaluate(PAGE_ACTIVITY_SCRIPT)
    except Exception:
        return {"unavailable": True}


async def _get_detections(driver, target_url):
    popup = await _ensure_popup(driver)
    selected_tab = await popup.evaluate(SELECT_TARGET_TAB_SCRIPT, target_url)

    if not selected_tab:
        return []

    detections = []
    last_signature = None
    last_activity_signature = None
    stable_polls = 0
    started_at = asyncio.get_running_loop().time()
    min_wait = 2.0
    hard_max = min(10.0, max(1.0, driver.timeout_ms / 1000 - 1))

    while True:
        response = await popup.evaluate(GET_DETECTIONS_FOR_TAB_SCRIPT, selected_tab)

        if isinstance(response, dict) and response.get("__error"):
            print(f"Wappalyzer extension error: {response['__error']}", file=sys.stderr)
            response = []

        detections = response if isinstance(response, list) else []
        signature = _detection_signature(detections)
        activity = await _page_activity(driver.page)
        activity_signature = _activity_signature(activity)

        if (
            signature == last_signature
            and activity_signature == last_activity_signature
        ):
            stable_polls += 1
        else:
            stable_polls = 0
            last_signature = signature
            last_activity_signature = activity_signature

        elapsed = asyncio.get_running_loop().time() - started_at
        page_quiet = _page_quiet(activity)
        stable_enough = stable_polls >= 2 and elapsed >= min_wait

        if stable_enough and page_quiet:
            break

        if elapsed >= hard_max:
            break

        await asyncio.sleep(0.5)

    return detections


async def process_url(driver, url):
    try:
        await driver.apply_pending_cookies(url)

        try:
            await driver.page.goto(
                url,
                wait_until="load",
                timeout=driver.timeout_ms,
            )
        except PlaywrightTimeoutError:
            try:
                await driver.page.evaluate("() => window.stop()")
            except Exception:
                pass

        await _stimulate_page(driver.page)

        return url, await _get_detections(driver, driver.page.url)
    except Exception:
        print(f"Error processing: {url}", file=sys.stderr)
        return url, []


def cookie_to_cookies(cookie):
    cookie_dict = SimpleCookie()
    cookie_dict.load(cookie)
    cookies = []

    for key, value in cookie_dict.items():
        cookies.append({
            "name": key,
            "value": value.value,
        })

    return cookies


def merge_technologies(detections):
    """wappalyzer produces duplicate results, we are merging them"""
    tech_map = {}

    for detection in detections:
        tech_name = detection["technology"]

        if tech_name not in tech_map:
            tech_map[tech_name] = {
                "version": detection.get("version", ""),
                "confidence": detection["pattern"]["confidence"],
            }
        else:
            existing = tech_map[tech_name]

            if not existing["version"] and detection.get("version"):
                existing["version"] = detection["version"]

            existing["confidence"] = min(
                existing["confidence"] + detection["pattern"]["confidence"],
                100,
            )

    return create_result(tech_map)
