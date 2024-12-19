import tldextract
import concurrent.futures
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from wappalyzer.parsers.js import get_js
from wappalyzer.parsers.dns import get_dns
from wappalyzer.parsers.meta import get_meta
from wappalyzer.parsers.robots import get_robots
from wappalyzer.parsers.scriptSrc import get_scriptSrc
from wappalyzer.parsers.certIssuer import get_certIssuer

from wappalyzer.core.matcher import match, match_dict
from wappalyzer.core.config import tech_db
from wappalyzer.analyzers.dom import match_dom
from wappalyzer.analyzers.js import match_js
from wappalyzer.core.requester import get_response
from wappalyzer.core.utils import create_result

def process_scripts(scheme, js, scriptSrc):
    def fetch_and_process(src):
        if src.endswith('.js') or '.js?' in src:
            js_code = get_response(src)
            if js_code and js_code.headers['Content-Type'].startswith('application/javascript'):
                js_dict, low_dict, js_classes = get_js(js_code.text)
                if js_dict:
                    return {'dict': js_dict, 'low_dict': low_dict, 'classes': js_classes, 'src': src}
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_and_process, src): src for src in scriptSrc}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                js.append({'dict': result['dict'], 'low_dict': result['low_dict'], 'classes': result['classes']})
                scriptSrc.extend(get_scriptSrc(scheme, get_response(result['src']).text))

def analyze_from_response(response, scan_type):
    # prepare common info
    soup = BeautifulSoup(response.text, 'html.parser')
    r = tldextract.extract(response.url)
    domain = r.domain + '.' + r.suffix
    scheme = urlparse(response.url).scheme
    hostname = urlparse(response.url).hostname
    base_url = f'{scheme}://{hostname}'

    js = []
    scriptSrc = get_scriptSrc(scheme, soup)
    for script in soup.find_all('script'):
        if not script.get('src'):
            js_dict, low_dict, js_classes = get_js(script.text)
            if js_dict:
                js.append({'dict': js_dict, 'low_dict': low_dict, 'classes': js_classes})
    if scan_type != 'fast':
        process_scripts(scheme, js, scriptSrc)

    if scan_type != 'fast':
        dns = get_dns(domain)
    meta = get_meta(soup)
    cookies = response.cookies.get_dict()
    if scan_type != 'fast':
        robots = get_robots(response.url)
    certIssuer = get_certIssuer(response)

    result = {}

    def update_entry(tech_name, version, confidence):
        if tech_name in result:
            result[tech_name]['confidence'] = min(result[tech_name]['confidence'] + confidence, 100)
            if version and not result[tech_name]['version']:
                result[tech_name]['version'] = version
        else:
            result[tech_name] = {'version': version, 'confidence': confidence}
        return result[tech_name]['confidence'] == 100

    for tech_name, tech_data in tech_db.items():
        if certIssuer and 'certIssuer' in tech_data:
            matched, version, confidence = match(tech_data['certIssuer'], certIssuer)
            if matched and update_entry(tech_name, version, confidence):
                continue
        if 'scriptSrc' in tech_data:
            for src in scriptSrc:
                matched, version, confidence = match(tech_data['scriptSrc'], src)
                if matched and update_entry(tech_name, version, confidence):
                    continue
        if 'dom' in tech_data:
            matched, version, confidence = match_dom(tech_data['dom'], soup)
            if matched and update_entry(tech_name, version, confidence):
                    continue
        if 'meta' in tech_data:
            matched, version, confidence = match_dict(tech_data['meta'], meta)
            if matched and update_entry(tech_name, version, confidence):
                continue
        if 'xhr' in tech_data:
            for x in scriptSrc:
                matched, version, confidence = match(tech_data['xhr'], x)
                if matched and update_entry(tech_name, version, confidence):
                    continue
        if 'html' in tech_data:
            matched, version, confidence = match(tech_data['html'], response.text)
            if matched and update_entry(tech_name, version, confidence):
                continue
        if 'js' in tech_data:
            matched, version, confidence = match_js(tech_data['js'], js)
            if matched and update_entry(tech_name, version, confidence):
                continue
        if 'cookies' in tech_data:
            matched, version, confidence = match_dict(tech_data['cookies'], cookies)
            if matched and update_entry(tech_name, version, confidence):
                continue
        if 'headers' in tech_data:
            matched, version, confidence = match_dict(tech_data['headers'], response.headers)
            if matched and update_entry(tech_name, version, confidence):
                continue
        if 'url' in tech_data:
            matched, version, confidence = match(tech_data['url'], response.url)
            if matched and update_entry(tech_name, version, confidence):
                continue
        if scan_type != 'fast' and 'dns' in tech_data:
            matched, version, confidence = match_dict(tech_data['dns'], dns)
            if matched and update_entry(tech_name, version, confidence):
                continue
        if scan_type != 'fast' and 'robots' in tech_data:
            matched, version, confidence = match(tech_data['robots'], robots)
            if matched and update_entry(tech_name, version, confidence):
                continue
    new_result = result.copy()
    for detected in result.keys():
        if 'implies' in tech_db[detected]:
            if type(tech_db[detected]['implies']) == list:
                for implied in tech_db[detected]['implies']:
                    new_result[implied] = {'version': '', 'confidence': 100}
            else:
                new_result[tech_db[detected]['implies']] = {'version': '', 'confidence': 100}
    return create_result(new_result)

def http_scan(url, scan_type, cookie=None):
    response = get_response(url, cookie)
    if response:
        return analyze_from_response(response, scan_type)
    return {}