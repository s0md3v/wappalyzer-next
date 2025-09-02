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
    if option.startswith('\\'):
        # when there is an optional group in the matching regex, that group may not exist.
        return match.group(int(option[1:])) or ''
    return option

def get_version(match, version_type):
    version = ''
    if version_type == '':
        return version
    if version_type.endswith(':'): # \\1?a:
        if match.group(1):
            version = group_or_literal(version_type.split('?')[-1].split(':')[0], match)
    elif '?:' in version_type: # \\1?:b'
        if not match.group(1):
            version = group_or_literal(version_type.split(':')[-1], match)
        else:
            version = ''
    elif ('?' and ':') in version_type: # \\1?a:b
        if match.group(1):
            version = group_or_literal(version_type.split('?')[-1].split(':')[0], match)
        else:
            version = group_or_literal(version_type.split(':')[-1], match)
    elif '\\' in version_type: # foo\\1
        if version_type.startswith('\\'):
            version = group_or_literal(version_type, match)
        else:
            version = version_type.split('\\')[0] + match.group(1)
    else:
        return version
    if version:
        version = re.split(r'[\)\]\},]', version.replace('\'', '').replace('"', ''))[0]
    return version

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
    to_match = [string] if isinstance(string, str) else string
    best_match = False
    best_version = ''
    best_confidence = 0

    for s in to_match:
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
