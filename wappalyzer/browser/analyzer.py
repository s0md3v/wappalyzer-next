import os
import json
import time
import re
import threading
from queue import Queue, Empty
from contextlib import contextmanager

from http.cookies import SimpleCookie
from urllib.parse import unquote
from json_repair import repair_json # type: ignore

from selenium import webdriver # type: ignore
from selenium.webdriver.firefox.options import Options # type: ignore
from selenium.webdriver.support import expected_conditions as EC # type: ignore
from selenium.webdriver.support.ui import WebDriverWait # type: ignore
from selenium.webdriver.common.by import By # type: ignore

from wappalyzer.core.config import extension_path # type: ignore
from wappalyzer.core.utils import create_result # type: ignore


class DriverPool:
    def __init__(self, size=3, max_retries=3):
        self.pool = Queue(maxsize=size)
        self.lock = threading.Lock()
        self.max_retries = max_retries
        self.xpi_path = os.path.abspath(extension_path)
        
        # Initialize the pool with drivers
        for _ in range(size):
            try:
                driver = self._create_driver()
                if driver:
                    self.pool.put(driver)
            except Exception as e:
                print(f"Failed to initialize driver: {str(e)}")

    def _create_driver(self):
        """Create a new Firefox driver with retry logic"""
        for attempt in range(self.max_retries):
            try:
                options = Options()
                # Keep existing options from init_firefox_driver
                options.set_preference("permissions.default.image", 2)
                options.set_preference("dom.ipc.plugins.enabled.libflashplayer.so", False)
                options.set_preference("media.video_stats.enabled", False)
                options.set_preference("media.autoplay.default", 5)
                options.set_preference("media.autoplay.blocking_policy", 2)
                options.set_preference("dom.webdriver.enabled", False)
                options.set_preference('useAutomationExtension', False)
                options.set_preference("general.useragent.override", 
                    "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0")
                options.add_argument("--headless")
                
                driver = webdriver.Firefox(options=options)
                driver.install_addon(self.xpi_path, temporary=True)
                driver.maximize_window()
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
                    driver.quit()  # Ensure driver is quit on error
                except:
                    pass
            raise
        finally:
            if driver:
                try:
                    # Reset driver state
                    driver.delete_all_cookies()
                    driver.execute_script("window.localStorage.clear();")
                    self.pool.put(driver)
                except Exception as e:
                    try:
                        driver.quit()  # Ensure driver is quit if we can't reuse it
                    except:
                        pass
                    # Try to create a new driver to replace the failed one
                    new_driver = self._create_driver()
                    if new_driver:
                        self.pool.put(new_driver)

    def cleanup(self):
        """Cleanup all drivers in the pool"""
        while True:
            try:
                driver = self.pool.get_nowait()
                try:
                    # Close all windows first
                    if hasattr(driver, 'window_handles'):
                        for handle in driver.window_handles:
                            driver.switch_to.window(handle)
                            driver.close()
                except:
                    pass
                finally:
                    try:
                        driver.quit()  # Always try to quit the driver
                    except:
                        pass
            except Empty:  # Use Empty directly
                break
            except Exception as e:
                print(f"Error during cleanup: {str(e)}")

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

def process_url(driver, url, timeout=150, threads=3):
    """
    Extracts components from the Wappalyzer extension while visiting a URL.
    Handles SPAs, multiple tabs, and potential errors.

    Args:
        driver: Selenium WebDriver instance.
        url (str): The target URL to process.
        timeout (int): Maximum wait time for SPAs.

    Returns:
        tuple: (URL, detected components from Wappalyzer)
    """
    try:
        #print(f"Processing URL: {url}")
        main_tab = driver.current_window_handle
        driver.get(url)

        # Wait for the page to load or SPA to render
        time.sleep(5)  # Initial wait for navigation

        try:
            WebDriverWait(driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            #print(f"Page loaded: {url}")
        except Exception:
            print(f"Page might still be loading (SPA detected?): {url}")

        # Give time for Wappalyzer to process
        for _ in range(5):
            driver.switch_to.window(main_tab)
            time.sleep(1)

        # Check all available windows
        current_handles = driver.window_handles

        if len(current_handles) > 1:
            rightmost_handle = current_handles[-1]
            driver.switch_to.window(rightmost_handle)
            result_url = driver.current_url

            if result_url.startswith("moz-extension://"):
                try:
                    decoded_url = unquote(result_url)

                    # Use regex to find a JSON-like structure
                    match = re.search(r"\{.*\}", decoded_url, re.DOTALL)

                    if not match:
                        print(f"No JSON found in response for {url}")
                        return url, []

                    raw_json = match.group(0)

                    good_json_string = repair_json(raw_json)
                    data = json.loads(good_json_string)

                    if not data:
                        return url, []

                    first_host = next(iter(data), None)
                    if not first_host:
                        print(f"No host found in extracted data for {url}.")
                        return url, []

                    first_result = data.get(first_host, {})
                    detections = first_result.get("detections", [])

                    #print(f"Detections found for {url}: {detections}")

                except (json.JSONDecodeError, ValueError) as json_error:
                    print(f"Error decoding JSON for {url}: {json_error}")
                    return url, []

                finally:
                    driver.close()
                    driver.switch_to.window(main_tab)

                return url, detections

            # Close the unused tab if it's not a Wappalyzer result
            driver.close()
            driver.switch_to.window(main_tab)

        return url, []

    except Exception as e:
        print(f"Error processing {url}: {e}", exc_info=True)
        return url, []

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
