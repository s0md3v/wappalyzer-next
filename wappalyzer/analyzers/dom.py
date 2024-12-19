from wappalyzer.core.matcher import parse_pattern

def query(soup, selector):
    try:
        return soup.select(selector)
    except Exception as e:
        return False

def match_dom(selectors, soup):
    if type(selectors) == str:
        clean_selector, version_type, confidence = parse_pattern(selectors)
        return query(soup, clean_selector), '', confidence
    elif type(selectors) == list:
        for selector in selectors:
            clean_selector, version_type, confidence = parse_pattern(selector)
            if query(soup, clean_selector):
                return True, '', confidence
    elif type(selectors) == dict:
        for name, selector in selectors.items():
            clean_selector, version_type, confidence = parse_pattern(selector)
            if query(soup, clean_selector):
                return True, '', confidence
    return False, '', 0