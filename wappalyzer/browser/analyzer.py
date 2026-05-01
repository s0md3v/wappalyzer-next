import os
import json
import re
import time
import threading
import concurrent.futures
from pathlib import Path
from queue import Queue, Empty
from contextlib import contextmanager

from http.cookies import SimpleCookie

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.firefox.options import Options

from wappalyzer.core.config import extension_path
from wappalyzer.core.utils import create_result


WAPPALYZER_EXTENSION_ID = "wappalyzer@crunchlabz.com"
WAPPALYZER_POPUP_PATH = "html/popup.html"
EXTENSION_UUIDS_PREF = re.compile(
    r'user_pref\("extensions\.webextensions\.uuids",\s*("(?:\\.|[^"\\])*")\);'
)

POPUP_HELPER_SCRIPT = """
if (!window.__wappalyzerGetDetectionsForTarget) {
  window.__wappalyzerGetDetectionsForTarget = async (targetUrl) => {
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

    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

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

    const selectTargetTab = async (target) => {
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

    const getDetections = async (selectedTab) => {
      const response = await sendMessage({
        source: 'popup.js',
        func: 'getDetectionsForTab',
        args: [{ id: selectedTab.id, url: selectedTab.url }],
      })

      if (response?.__error) {
        return response
      }

      return Array.isArray(response)
        ? response
        : Array.isArray(response?.detections)
          ? response.detections
          : []
    }

    const detectionSignature = (detections) =>
      detections
        .map((detection) => {
          const technology = detection?.technology
          const technologyName =
            technology && typeof technology === 'object'
              ? technology.name
              : technology || detection?.name || detection?.slug

          if (!technologyName) {
            return ''
          }

          return [
            technologyName,
            detection.version || '',
            detection.pattern?.confidence ?? detection.confidence ?? '',
          ].join(':')
        })
        .filter(Boolean)
        .sort()
        .join('|')

    const target = parseUrl(targetUrl)

    if (!target || !/^https?:$/.test(target.protocol)) {
      return []
    }

    const selectedTab = await selectTargetTab(target)

    if (!selectedTab) {
      return []
    }

    let detections = []
    let lastSignature = ''
    let stablePolls = 0
    const startedAt = Date.now()

    for (let attempt = 0; attempt < 12; attempt += 1) {
      const response = await getDetections(selectedTab)

      if (response?.__error) {
        return { error: response.__error }
      }

      detections = response
      const signature = detectionSignature(detections)

      if (signature && signature === lastSignature) {
        stablePolls += 1
      } else {
        stablePolls = 0
        lastSignature = signature
      }

      if (signature && stablePolls >= 2 && Date.now() - startedAt >= 2000) {
        break
      }

      await sleep(500)
    }

    return detections
      .filter(
        (detection) =>
          detection?.technology || detection?.name || detection?.slug
      )
      .map(normaliseDetection)
  }
}
"""

GET_DETECTIONS_SCRIPT = """
const targetUrl = arguments[0]
const done = arguments[arguments.length - 1]

;(async () => {
  if (!window.__wappalyzerGetDetectionsForTarget) {
    done({ error: 'Wappalyzer popup helper is not installed' })

    return
  }

  done(await window.__wappalyzerGetDetectionsForTarget(targetUrl))
})().catch((error) => done({ error: error.message || String(error) }))
"""


def _extension_uuid_from_pref(text, addon_ids):
    match = EXTENSION_UUIDS_PREF.search(text)

    if not match:
        return None

    try:
        uuids = json.loads(json.loads(match.group(1)))
    except (TypeError, ValueError):
        return None

    for addon_id in addon_ids:
        if addon_id and addon_id in uuids:
            return uuids[addon_id]

    return None


def _get_extension_uuid(driver, timeout=5):
    cached = getattr(driver, "_wappalyzer_extension_uuid", None)

    if cached:
        return cached

    profile_dir = driver.capabilities.get("moz:profile")

    if not profile_dir:
        return None

    addon_ids = (
        getattr(driver, "_wappalyzer_extension_id", None),
        WAPPALYZER_EXTENSION_ID,
    )
    prefs_path = Path(profile_dir) / "prefs.js"
    deadline = time.time() + timeout

    while time.time() < deadline:
        if prefs_path.exists():
            uuid = _extension_uuid_from_pref(
                prefs_path.read_text(encoding="utf-8", errors="ignore"),
                addon_ids,
            )

            if uuid:
                driver._wappalyzer_extension_uuid = uuid

                return uuid

        time.sleep(0.1)

    return None


def _get_popup_url(driver):
    extension_uuid = _get_extension_uuid(driver)

    if not extension_uuid:
        raise RuntimeError("Unable to resolve Wappalyzer Firefox extension UUID")

    return f"moz-extension://{extension_uuid}/{WAPPALYZER_POPUP_PATH}"


def _close_extra_tabs(driver, keep_handle, keep_handles=None):
    keep_handles = set(keep_handles or ())
    keep_handles.add(keep_handle)

    for handle in list(driver.window_handles):
        if handle in keep_handles:
            continue

        try:
            driver.switch_to.window(handle)
            driver.close()
        except Exception:
            pass

    if keep_handle in driver.window_handles:
        driver.switch_to.window(keep_handle)


def _install_popup_helper(driver):
    driver.execute_script(POPUP_HELPER_SCRIPT)
    driver._wappalyzer_popup_helper_installed = True


def _get_target_tab(driver):
    popup_handle = getattr(driver, "_wappalyzer_popup_handle", None)

    try:
        current_handle = driver.current_window_handle
    except Exception:
        current_handle = None

    if current_handle and current_handle != popup_handle:
        return current_handle

    for handle in driver.window_handles:
        if handle != popup_handle:
            driver.switch_to.window(handle)

            return handle

    driver.switch_to.new_window("tab")

    return driver.current_window_handle


def _ensure_popup_tab(driver):
    popup_url = _get_popup_url(driver)
    popup_handle = getattr(driver, "_wappalyzer_popup_handle", None)

    if popup_handle in driver.window_handles:
        driver.switch_to.window(popup_handle)

        if driver.current_url != popup_url:
            driver.get(popup_url)
            driver._wappalyzer_popup_helper_installed = False

        if not getattr(driver, "_wappalyzer_popup_helper_installed", False):
            _install_popup_helper(driver)

        return popup_handle

    driver.switch_to.new_window("tab")
    driver._wappalyzer_popup_handle = driver.current_window_handle
    driver.get(popup_url)
    driver._wappalyzer_popup_helper_installed = False
    _install_popup_helper(driver)

    return driver._wappalyzer_popup_handle


def _get_detections_for_current_tab(driver, target_url):
    main_tab = driver.current_window_handle

    try:
        _ensure_popup_tab(driver)

        detections = driver.execute_async_script(
            GET_DETECTIONS_SCRIPT,
            target_url,
        )

        if isinstance(detections, dict):
            if detections.get("error"):
                print(f"Wappalyzer extension error: {detections['error']}")

            detections = detections.get("detections", [])

        return detections if isinstance(detections, list) else []
    finally:
        if main_tab in driver.window_handles:
            driver.switch_to.window(main_tab)


def _stimulate_page(driver, max_duration_ms=1250):
    if max_duration_ms <= 0:
        return

    script = """
const maxDuration = arguments[0]

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
"""

    try:
        driver.execute_script(script, max_duration_ms)
    except Exception:
        pass


def _quit_driver(driver, timeout=3):
    done = threading.Event()

    def quit_driver():
        try:
            driver.quit()
        except Exception:
            pass
        finally:
            done.set()

    thread = threading.Thread(target=quit_driver, daemon=True)
    thread.start()
    thread.join(timeout)

    if done.is_set():
        return

    service = getattr(driver, "service", None)
    process = getattr(service, "process", None)

    if not process:
        return

    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except Exception:
                if process.poll() is None:
                    process.kill()
    except Exception:
        pass


class DriverPool:
    def __init__(self, size=3, max_retries=3, timeout=30):
        self.pool = Queue(maxsize=size)
        self.lock = threading.Lock()
        self.max_retries = max_retries
        self.timeout = timeout
        self.closed = False
        self.xpi_path = os.path.abspath(extension_path)
        
        # Initialize the pool with drivers
        if size <= 1:
            try:
                driver = self._create_driver()
                if driver:
                    self.pool.put(driver)
            except Exception as e:
                print(f"Failed to initialize driver: {str(e)}")
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=size) as executor:
                futures = [executor.submit(self._create_driver) for _ in range(size)]

                for future in concurrent.futures.as_completed(futures):
                    try:
                        driver = future.result()
                        if driver:
                            with self.lock:
                                if self.closed:
                                    should_quit = True
                                else:
                                    should_quit = False
                                    self.pool.put(driver)

                            if should_quit:
                                _quit_driver(driver)
                    except Exception as e:
                        print(f"Failed to initialize driver: {str(e)}")

    def _create_driver(self):
        """Create a new Firefox driver with retry logic"""
        for attempt in range(self.max_retries):
            try:
                options = Options()
                # Keep existing options from init_firefox_driver
                options.set_preference("accessibility.force_disabled", 1)
                options.set_preference("permissions.default.image", 2)
                options.set_preference("permissions.default.desktop-notification", 2)
                options.set_preference("permissions.default.geo", 2)
                options.set_preference("browser.shell.checkDefaultBrowser", False)
                options.set_preference("browser.startup.homepage_override.mstone", "ignore")
                options.set_preference("startup.homepage_welcome_url", "about:blank")
                options.set_preference("startup.homepage_welcome_url.additional", "")
                options.set_preference("dom.ipc.plugins.enabled.libflashplayer.so", False)
                options.set_preference("gfx.downloadable_fonts.enabled", False)
                options.set_preference("media.video_stats.enabled", False)
                options.set_preference("media.autoplay.default", 5)
                options.set_preference("media.autoplay.blocking_policy", 2)
                options.set_preference("media.preload.default", 0)
                options.set_preference("browser.safebrowsing.malware.enabled", False)
                options.set_preference("browser.safebrowsing.phishing.enabled", False)
                options.set_preference("browser.safebrowsing.downloads.enabled", False)
                options.set_preference("datareporting.healthreport.uploadEnabled", False)
                options.set_preference("datareporting.policy.dataSubmissionEnabled", False)
                options.set_preference("toolkit.telemetry.enabled", False)
                options.set_preference("dom.webdriver.enabled", False)
                options.set_preference('useAutomationExtension', False)
                options.set_preference("general.useragent.override", 
                    "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0")
                options.add_argument("--headless")
                options.add_argument("--width=1366")
                options.add_argument("--height=900")

                driver = webdriver.Firefox(options=options)
                driver._wappalyzer_extension_id = driver.install_addon(
                    self.xpi_path,
                    temporary=True,
                )
                driver.set_page_load_timeout(self.timeout)
                driver.set_script_timeout(max(5, min(self.timeout, 15)))
                _get_extension_uuid(driver)
                return driver
            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {str(e)}")
                time.sleep(1)
                
        return None

    @contextmanager
    def get_driver(self):
        """Get a driver from the pool with proper resource management"""
        driver = None
        try:
            driver = self.pool.get(timeout=30)  # Wait up to 30 seconds for a driver
            yield driver
        except Exception as e:
            print(f"Error with driver: {str(e)}")
            if driver:
                try:
                    _quit_driver(driver)  # Ensure driver is quit on error
                except:
                    pass
            raise
        finally:
            if driver:
                reusable = True
                try:
                    # Reset driver state
                    driver.delete_all_cookies()
                    driver.execute_script("window.localStorage.clear();")
                except Exception as e:
                    reusable = False

                if reusable:
                    should_quit = False
                    with self.lock:
                        if self.closed:
                            should_quit = True
                        else:
                            self.pool.put(driver)

                    if should_quit:
                        try:
                            _quit_driver(driver)
                        except:
                            pass
                else:
                    try:
                        _quit_driver(driver)  # Ensure driver is quit if we can't reuse it
                    except:
                        pass

                    with self.lock:
                        should_replace = not self.closed

                    if should_replace:
                        # Try to create a new driver to replace the failed one
                        new_driver = self._create_driver()
                        if new_driver:
                            should_quit = False
                            with self.lock:
                                if self.closed:
                                    should_quit = True
                                else:
                                    self.pool.put(new_driver)

                            if should_quit:
                                try:
                                    _quit_driver(new_driver)
                                except:
                                    pass

    def cleanup(self):
        """Cleanup all drivers in the pool"""
        with self.lock:
            if self.closed:
                return

            self.closed = True
        drivers = []

        while True:
            try:
                driver = self.pool.get_nowait()
                drivers.append(driver)
            except Empty:  # Use Empty directly
                break
            except Exception as e:
                print(f"Error during cleanup: {str(e)}")

        def quit_driver(driver):
            try:
                _quit_driver(driver)
            except:
                pass

        threads = []

        for driver in drivers:
            thread = threading.Thread(target=quit_driver, args=(driver,))
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()

    def __del__(self):
        """Destructor to ensure cleanup"""
        self.cleanup()

def cookie_to_cookies(cookie):
    cookie_dict = SimpleCookie().load(cookie)
    cookies = []
    if cookie_dict:
        for key, value in cookie_dict.items():
            cookies.append({
                'name': key,
                'value': value
            })
    return cookies

def process_url(driver, url):
    main_tab = _get_target_tab(driver)

    try:
        popup_handle = getattr(driver, "_wappalyzer_popup_handle", None)
        keep_handles = {popup_handle} if popup_handle in driver.window_handles else set()
        _close_extra_tabs(driver, main_tab, keep_handles)
        
        try:
            driver.get(url)
        except TimeoutException:
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass

        _stimulate_page(driver)

        return url, _get_detections_for_current_tab(driver, driver.current_url)
        
    except Exception as e:
        print(f"Error processing: {url}")
        return url, []
    finally:
        popup_handle = getattr(driver, "_wappalyzer_popup_handle", None)
        keep_handles = {popup_handle} if popup_handle in driver.window_handles else set()
        _close_extra_tabs(driver, main_tab, keep_handles)

def merge_technologies(detections):
    """wappalyzer produces duplicate results, we are merging them"""
    tech_map = {}
    
    for detection in detections:
        tech_name = detection['technology']
        
        if tech_name not in tech_map:
            tech_map[tech_name] = {
                'version': detection.get('version', ''),
                'confidence': detection['pattern']['confidence']
            }
        else:
            existing = tech_map[tech_name]
            # keep the non-empty version
            if not existing['version'] and detection.get('version'):
                existing['version'] = detection['version']
            # add confidences, capping at 100
            existing['confidence'] = min(
                existing['confidence'] + detection['pattern']['confidence'],
                100
            )
    
    return create_result(tech_map)
