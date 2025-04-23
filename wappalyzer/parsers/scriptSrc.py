import re
from urllib.parse import urljoin, urlparse

url_pattern = r'(?:https?:)?//[\w.-]{2,}\.[a-zA-Z]{2,63}(?:[^\'"\s\n]+)?'

def get_urls_from_js(scheme, js, base_url=None):
    scriptSrc = []
    matches = re.findall(url_pattern, js)
    for each in matches:
        if each.startswith('//'):
            each = scheme + ':' + each
        scriptSrc.append(each)
    return scriptSrc

def get_scriptSrc(scheme, soup, url=None):
    if type(soup) == str:
        return get_urls_from_js(scheme, soup)

    # Get base URL from the current page's URL or the base element
    base_url = None
    if url:
        # Extract the base URL from the page URL
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
        # Remove filename from path if present
        if base_url.rsplit('/', 1)[-1] and '.' in base_url.rsplit('/', 1)[-1]:
            base_url = base_url.rsplit('/', 1)[0] + '/'
    
    # Check for a base tag in the HTML
    base_tag = soup.find('base', href=True)
    if base_tag:
        base_url = base_tag['href']
    elif not base_url and scheme and hasattr(soup, 'url'):
        # Try to use the soup's URL if available (BeautifulSoup with response object)
        parsed_url = urlparse(soup.url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

    scriptSrc = []
    for script in soup.find_all('script'):
        src = script.get('src')
        if src:
            if src.startswith('//'):
                src = scheme + ':' + src
            elif not (src.startswith('http://') or src.startswith('https://')):
                # Handle relative URLs by joining with base URL
                if base_url:
                    src = urljoin(base_url, src)
                else:
                    # If we can't resolve the URL properly, skip it
                    continue
            scriptSrc.append(src)
        else:
            scriptSrc.extend(get_urls_from_js(scheme, script.text))
    return scriptSrc