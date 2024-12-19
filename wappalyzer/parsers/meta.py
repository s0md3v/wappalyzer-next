def get_meta(soup):
    meta = {}
    for tag in soup.find_all('meta'):
        meta[tag.get('name')] = tag.get('content')
    return meta