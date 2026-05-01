import re

"""
Special strings: version, confidence

\\;confidence:50
jquery-([0-9.]+).js\\;version:\\1

\\1      Returns the first match.
\\1?a:   Returns a if the first match contains a value, nothing otherwise.
\\1?a:b  Returns a if the first match contains a value, b otherwise.
\\1?:b   Returns nothing if the first match contains a value, b otherwise.
foo\\1   Returns foo with the first match appended.
"""

def group_or_literal(option, match):
    def replace_group(group_match):
        try:
            return match.group(int(group_match.group(1))) or ''
        except (IndexError, ValueError):
            return ''

    return re.sub(r'\\(\d+)', replace_group, option)

def get_version(match, version_type):
    version = ''
    if version_type == '':
        return version
    if '?:' in version_type: # \\1?:b
        condition, fallback = version_type.split('?:', 1)
        if not group_or_literal(condition, match):
            version = group_or_literal(fallback, match)
    elif '?' in version_type and ':' in version_type: # \\1?a:b or \\1?a:
        condition, choices = version_type.split('?', 1)
        truthy, falsy = choices.split(':', 1)
        version = group_or_literal(
            truthy if group_or_literal(condition, match) else falsy,
            match,
        )
    else:
        version = group_or_literal(version_type, match)
    if version:
        version = re.split(r'[\)\]\},]', version.replace('\'', '').replace('"', ''))[0]
    return version

def normalize_match_value(value):
    if isinstance(value, bool):
        return str(value).lower()
    if value is None:
        return ''
    return str(value)

def parse_pattern(regex):
    confidence = 100
    clean_regex = regex
    if '\\;confidence:' in clean_regex:
        this_match = re.search(r'\\;confidence:(\d+)', regex)
        confidence = int(this_match.group(1).strip())
        clean_regex = clean_regex.replace(this_match.group(0), '')
    version_type = ''
    if '\\;version:' in clean_regex:
        version_type = clean_regex.split('\\;version:')[1]
        clean_regex = clean_regex.split('\\;version:')[0]
    return clean_regex, version_type, confidence

def single_match(regex, string):
    clean_regex, version_type, confidence = parse_pattern(regex)

    this_match = ''
    try:
        this_match = re.search(clean_regex, string)
    except Exception as e:
        if 're.error: bad escape' in str(e):
            problem = re.search(r'bad escape (.)', str(e)).group(1)
            this_match = re.search(clean_regex.replace(problem, '\\' + problem), string)
    if this_match:
        return True, get_version(this_match, version_type), confidence
    return False, '', 0

def match(regex, string):
    if isinstance(string, (list, tuple, set)):
        to_match = string
    else:
        to_match = [string]
    best_match = False
    best_version = ''
    best_confidence = 0

    for s in to_match:
        if not isinstance(s, str):
            s = normalize_match_value(s)
        regexes = [regex] if isinstance(regex, str) else regex
        for r in regexes:
            this_match, version, confidence = single_match(r, s)
            if this_match:
                if (confidence > best_confidence) or (confidence == best_confidence and version > best_version):
                    best_match = True
                    best_version = version
                    best_confidence = confidence

    return best_match, best_version, best_confidence


def match_dict(pattern_dict, response_dict):
    for name, pattern in pattern_dict.items():
        if name in response_dict:
            values = response_dict[name]
            if not isinstance(values, list):
                values = [values]
            for value in values:
                if pattern == '':
                    return True, '', 100
                matched, version, confidence = match(pattern, value)
                if matched:
                    return True, version, confidence
    return False, '', 0
