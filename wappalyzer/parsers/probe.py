from urllib.parse import urlparse

def get_probe(url):
    scheme = urlparse(url).scheme
    hostname = urlparse(url).hostname
    probe_url = f'{scheme}://{hostname}'
    return probe_url