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
        return match.group(int(option[1:]))
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
    to_match = [string] if type(string) == str else string
    for string in to_match:
        if type(regex) == str:
            return single_match(regex, string)
        for r in regex:
            this_match, version, confidence = single_match(r, string)
            if this_match:
                return this_match, version, confidence
    return False, '', 0

def match_dict(pattern_dict, response_dict):
    for name, pattern in pattern_dict.items():
        if name in response_dict:
            if pattern_dict[name] == '':
                return True, '', 100
            matched, version, confidence = match(pattern, response_dict[name])
            if matched:
                return True, version, confidence
    return False, '', 0