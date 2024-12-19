from wappalyzer.core.matcher import match_dict

def fix_keys(pattern, js, classes):
    new_js = js.copy()
    for key, value in pattern.items():
        if '.' in key:
            for k, v in js.items():
                if k in key and all([c in classes for c in key.split('.')]):
                    new_js[key] = new_js.pop(k)
                    break
    for k, v in js.items():
        if len(k) <= 2 and k in new_js and not v:
            new_js.pop(k)
    return new_js

def match_js(pattern, js):
    for js_dict in js:
        js, low_js, classes = js_dict['dict'], js_dict['low_dict'], js_dict['classes']
        js = fix_keys(pattern, js, classes)
        low_js = fix_keys(pattern, low_js, classes)
        for key in low_js.copy().keys():
            if key in js:
                del low_js[key]
        matched, version, confidence = match_dict(pattern, js)
        if matched:
            return matched, version, confidence
    return False, '', 0