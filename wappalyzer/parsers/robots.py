from urllib.parse import urlparse
from wappalyzer.core.requester import get_response

def get_robots(url):
    scheme = urlparse(url).scheme
    hostname = urlparse(url).hostname
    robots_url = f'{scheme}://{hostname}/robots.txt'
    r = get_response(robots_url)
    return r.text if r else ''