import re
from urllib.parse import urljoin, urlparse

url_pattern = r'(?:https?:)?//[\w.-]{2,}\.[a-zA-Z]{2,63}(?:[^\'"\s\n]+)?'

def get_urls_from_js(base_url, js):
    scriptSrc = []
    matches = re.findall(url_pattern, js)
    for each in matches:
        if each.startswith('//'):
            scheme = urlparse(base_url).scheme
            each = scheme + ':' + each
        scriptSrc.append(each)
    return scriptSrc

def get_scriptSrc(base_url, soup):
    if type(soup) == str:
        return get_urls_from_js(base_url, soup)

    scheme = urlparse(base_url).scheme
    scriptSrc = []
    for script in soup.find_all('script'):
        src = script.get('src')
        if src:
            # Use urljoin to handle all types of URLs (absolute, protocol-relative, and path-relative)
            src = urljoin(base_url, src)
            scriptSrc.append(src)
        else:
            scriptSrc.extend(get_urls_from_js(base_url, script.text))
    return scriptSrc