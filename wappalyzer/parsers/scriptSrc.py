import re

url_pattern = r'(?:https?:)?//[\w.-]{2,}\.[a-zA-Z]{2,63}(?:[^\'"\s\n]+)?'

def get_urls_from_js(scheme, js):
    scriptSrc = []
    matches = re.findall(url_pattern, js)
    for each in matches:
        if each.startswith('//'):
            each = scheme + ':' + each
        scriptSrc.append(each)
    return scriptSrc

def get_scriptSrc(scheme, soup):
    if type(soup) == str:
        return get_urls_from_js(scheme, soup)

    scriptSrc = []
    for script in soup.find_all('script'):
        src = script.get('src')
        if src:
            if src.startswith('//'):
                src = scheme + ':' + src
            scriptSrc.append(src)
        else:
            scriptSrc.extend(get_urls_from_js(scheme, script.text))
    return scriptSrc