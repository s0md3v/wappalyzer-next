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
    excluded = []
    implied = []
    required = []
    for tech_name, value in technologies.items():
        this_tech = value.copy()
        if tech_name not in tech_db:
            this_tech['categories'], this_tech['groups'] = [], []
            continue
        this_tech['categories'], this_tech['groups'] = get_cats_and_groups(tech_name)
        if 'requires' in tech_db[tech_name]:
            if type(tech_db[tech_name]["requires"]) == list:
                required.extend(tech_db[tech_name]['requires'])
            else:
                required.append(tech_db[tech_name]['requires'])
        if 'implies' in tech_db[tech_name]:
            if type(tech_db[tech_name]['implies']) == list:
                implied.extend(tech_db[tech_name]['implies'])
            else:
                implied.append(tech_db[tech_name]['implies'])
        if 'excludes' in tech_db[tech_name]:
            if type(tech_db[tech_name]['excludes']) == list:
                excluded.extend(tech_db[tech_name]['excludes'])
            else:
                excluded.append(tech_db[tech_name]['excludes'])
        enriched[tech_name] = this_tech

    for tech in list(set(required).union(set(implied) - set(excluded))):
        if tech not in enriched:
            enriched[tech] = {
                'version': '',
                'confidence': 100,
                'categories': get_cats_and_groups(tech)[0],
                'groups': get_cats_and_groups(tech)[1]
            }
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

def generate_html_report(data):
    html_template = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>wappalyzer results</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        .controls {
            margin-bottom: 20px;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .search-container {
            display: flex;
            gap: 10px;
            align-items: flex-start;
        }
        .search-wrapper {
            position: relative;
            flex-grow: 1;
        }
        .search-box {
            padding: 8px;
            width: 100%;
            border: 1px solid #ccc;
            border-radius: 4px;
        }
        .autocomplete-list {
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            background: white;
            border: 1px solid #ddd;
            border-radius: 4px;
            max-height: 200px;
            overflow-y: auto;
            z-index: 1000;
            display: none;
        }
        .autocomplete-item {
            padding: 8px;
            cursor: pointer;
        }
        .autocomplete-item:hover {
            background-color: #f0f0f0;
        }
        .tags-container {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }
        .tag {
            background-color: #e0e0e0;
            border-radius: 16px;
            padding: 4px 12px;
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.9em;
        }
        .tag-remove {
            cursor: pointer;
            color: #666;
            font-weight: bold;
        }
        .tag-remove:hover {
            color: #333;
        }
        button {
            padding: 8px 16px;
            background-color: #4CAF50;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            white-space: nowrap;
        }
        button:hover {
            background-color: #45a049;
        }
        .results {
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 20px;
        }
        .site {
            margin-bottom: 20px;
            display: none;
        }
        .site.visible {
            display: block;
        }
        .site-url {
            font-size: 1.2em;
            color: #2196F3;
            margin-bottom: 10px;
            font-weight: bold;
        }
        .tech-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 10px;
        }
        .tech-item {
            padding: 8px;
            background-color: #f5f5f5;
            border-radius: 4px;
            font-size: 0.9em;
        }
        .tech-name {
            font-weight: bold;
        }
        .tech-meta {
            color: #666;
            font-size: 0.9em;
        }
    </style>
</head>
<body>    
    <div class="controls">
        <div class="search-container">
            <div class="search-wrapper">
                <input type="text" id="searchInput" class="search-box" placeholder="Search technologies or URLs...">
                <div id="autocompleteList" class="autocomplete-list"></div>
            </div>
            <button onclick="downloadUrls()">Download URLs</button>
        </div>
        <div id="tagsContainer" class="tags-container"></div>
    </div>
    
    <div class="results" id="results">
    '''
    
    for url, technologies in data.items():
        html_template += f'''
        <div class="site" data-url="{url.lower()}">
            <div class="site-url">{url}</div>
            <div class="tech-grid">
        '''
        
        for tech_name, tech_info in technologies.items():
            version = f" v{tech_info['version']}" if tech_info['version'] else ""
            categories = ', '.join(tech_info['categories'])
            groups = ', '.join(tech_info['groups'])
            
            html_template += f'''
            <div class="tech-item" data-tech="{tech_name.lower()}">
                <div class="tech-name">{tech_name}{version}</div>
                <div class="tech-meta">
                    {categories} | {groups}
                </div>
            </div>
            '''
        
        html_template += '''
            </div>
        </div>
        '''
    
    html_template += '''
    </div>

    <script>
        let activeTags = new Set();
        let allTechnologies = new Set();
        
        // Initialize technologies set
        function initializeTechnologies() {
            const techItems = document.getElementsByClassName('tech-item');
            Array.from(techItems).forEach(item => {
                const techName = item.querySelector('.tech-name').textContent.split(' v')[0];
                allTechnologies.add(techName);
            });
        }
        
        // Initial setup - show all sites
        function initializeSites() {
            const sites = document.getElementsByClassName('site');
            Array.from(sites).forEach(site => site.classList.add('visible'));
            initializeTechnologies();
        }
        
        // Autocomplete functionality
        function showAutocomplete(searchTerm) {
            const autocompleteList = document.getElementById('autocompleteList');
            autocompleteList.innerHTML = '';
            
            if (!searchTerm) {
                autocompleteList.style.display = 'none';
                return;
            }
            
            const matches = Array.from(allTechnologies)
                .filter(tech => tech.toLowerCase().includes(searchTerm.toLowerCase()))
                .filter(tech => !activeTags.has(tech));
                
            if (matches.length === 0) {
                autocompleteList.style.display = 'none';
                return;
            }
            
            matches.forEach(tech => {
                const item = document.createElement('div');
                item.className = 'autocomplete-item';
                item.textContent = tech;
                item.onclick = () => addTag(tech);
                autocompleteList.appendChild(item);
            });
            
            autocompleteList.style.display = 'block';
        }
        
        // Add tag
        function addTag(technology) {
            if (activeTags.has(technology)) return;
            
            activeTags.add(technology);
            const tagsContainer = document.getElementById('tagsContainer');
            
            const tag = document.createElement('div');
            tag.className = 'tag';
            tag.innerHTML = `
                ${technology}
                <span class="tag-remove" onclick="removeTag('${technology}')">&times;</span>
            `;
            
            tagsContainer.appendChild(tag);
            document.getElementById('searchInput').value = '';
            document.getElementById('autocompleteList').style.display = 'none';
            updateResults();
        }
        
        // Remove tag
        function removeTag(technology) {
            activeTags.delete(technology);
            const tagsContainer = document.getElementById('tagsContainer');
            const tags = tagsContainer.getElementsByClassName('tag');
            
            Array.from(tags).forEach(tag => {
                if (tag.textContent.trim().includes(technology)) {
                    tag.remove();
                }
            });
            
            updateResults();
        }
        
        // Update results based on active tags
        function updateResults() {
            const sites = document.getElementsByClassName('site');
            
            Array.from(sites).forEach(site => {
                const techItems = site.getElementsByClassName('tech-item');
                let hasAllTags = true;
                
                if (activeTags.size === 0) {
                    site.classList.add('visible');
                    return;
                }
                
                for (let tag of activeTags) {
                    let hasTag = false;
                    Array.from(techItems).forEach(item => {
                        const techName = item.querySelector('.tech-name').textContent.split(' v')[0];
                        if (techName === tag) {
                            hasTag = true;
                        }
                    });
                    if (!hasTag) {
                        hasAllTags = false;
                        break;
                    }
                }
                
                if (hasAllTags) {
                    site.classList.add('visible');
                } else {
                    site.classList.remove('visible');
                }
            });
        }
        
        // Search input event handlers
        document.getElementById('searchInput').addEventListener('input', function(e) {
            showAutocomplete(e.target.value);
        });
        
        document.addEventListener('click', function(e) {
            if (!e.target.closest('.search-wrapper')) {
                document.getElementById('autocompleteList').style.display = 'none';
            }
        });

        // Download URLs functionality
        function downloadUrls() {
            const visibleSites = Array.from(document.getElementsByClassName('site'))
                .filter(site => site.classList.contains('visible'));
            
            let urls = visibleSites.map(site => site.getAttribute('data-url'));
            let content = urls.join('\\n');
            
            const blob = new Blob([content], { type: 'text/plain' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.setAttribute('href', url);
            a.setAttribute('download', 'matched_urls.txt');
            a.click();
        }
        
        // Initialize on page load
        initializeSites();
    </script>
</body>
</html>
    '''
    
    return html_template

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
    elif format == 'html':
        html_content = generate_html_report(data)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
