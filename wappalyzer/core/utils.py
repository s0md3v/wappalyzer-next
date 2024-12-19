import json
from huepy import bold, green
from wappalyzer.core.config import cat_db, groups_db, tech_db

def get_cats_and_groups(tech_name):
    cats = []
    groups = []
    for cat in tech_db[tech_name]['cats']:
        cats.append(cat_db[str(cat)]['name'])
        for group in cat_db[str(cat)]['groups']:
            this_group = groups_db[str(group)]['name']
            if this_group not in groups:
                groups.append(this_group)
    return cats, groups

def create_result(technologies):
    enriched = {}
    for tech_name, value in technologies.items():
        this_tech = value.copy()
        if tech_name not in tech_db:
            this_tech['categories'], this_tech['groups'] = [], []
            continue
        this_tech['categories'], this_tech['groups'] = get_cats_and_groups(tech_name)
        enriched[tech_name] = this_tech
    return enriched

def pretty_print(result):
    for url, value in result.items():
        output_string = bold(green(url)) + ' '
        for name, data in value.items():
            if data['version']:
                output_string += f"{name} v{data['version']}, "
            else:
                output_string += f"{name}, "
        print(output_string.rstrip(', '))

def write_to_file(filepath, data, format='json'):
    if format == 'json':
        with open(filepath, 'w+') as f:
            json.dump(data, f)
    elif format == 'csv':
        url = list(data.keys())[0]
        with open(filepath, 'w+') as f:
            for tech, tech_data in data[url].items():
                csv_data = url + ',' + tech + ',' + tech_data['version'] + ',' + str(tech_data['confidence']) + ',' + ' '.join(tech_data['categories']) + ',' + ' '.join(tech_data['groups']) + '\n'
                f.write(csv_data)
