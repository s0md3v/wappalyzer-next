import os
import json
import time

from http.cookies import SimpleCookie
from urllib.parse import unquote

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By

from wappalyzer.core.config import extension_path
from wappalyzer.core.utils import create_result


def init_firefox_driver(cookies):
    """Initialize Firefox with Wappalyzer extension and optimized settings"""
    options = Options()
    
    # performance and stealth tweaks
    options.set_preference("permissions.default.image", 2)
    options.set_preference("dom.ipc.plugins.enabled.libflashplayer.so", False)
    options.set_preference("media.video_stats.enabled", False)
    options.set_preference("media.autoplay.default", 5)
    options.set_preference("media.autoplay.blocking_policy", 2)
    options.set_preference("dom.webdriver.enabled", False)
    options.set_preference('useAutomationExtension', False)
    options.set_preference("general.useragent.override", "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0")
    options.add_argument("--headless")
    
    xpi_path = os.path.abspath(extension_path)
    
    driver = webdriver.Firefox(options=options)
    for cookie in cookies:
        driver.add_cookie(cookie)
    driver.install_addon(xpi_path, temporary=True)
    driver.maximize_window()
    
    return driver

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
    try:
        main_tab = driver.current_window_handle
        initial_handles = set(driver.window_handles)
        
        driver.get(url)
        
        for i in range(5):
            driver.switch_to.window(main_tab)
            time.sleep(1)
        
        # after 5 seconds, process the right-most tab
        current_handles = driver.window_handles
        if len(current_handles) > 1:
            rightmost_handle = current_handles[-1]
            driver.switch_to.window(rightmost_handle)
            
            result_url = driver.current_url
            if result_url.startswith("moz-extension://"):
                decoded = '{' + unquote(result_url).split('{', 1)[1]
                data = json.loads(decoded)
                first_host = next(iter(data))
                first_result = data[first_host]
                
                driver.close()
                driver.switch_to.window(current_handles[0])
                
                return url, first_result['detections']
            
            driver.close()
            driver.switch_to.window(current_handles[0])
        
        return url, []
        
    except Exception as e:
        print(f"Error processing {url}: {str(e)}")
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
