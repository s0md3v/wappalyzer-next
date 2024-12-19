def get_css(soup):
    css = []
    for link in soup.find_all('style'):
        css.append(link.text)
    return css