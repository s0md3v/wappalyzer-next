#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import io
from setuptools import setup, find_packages
from os import path
this_directory = path.abspath(path.dirname(__file__))
with io.open(path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    desc = f.read()

setup(
    name='wappalyzer',
    version='1.0.14',
    description='Wappalyzer-based tech stack detection library',
    long_description=desc,
    long_description_content_type='text/markdown',
    author='Somdev Sangwan',
    author_email='s0md3v@gmail.com',
    license='GNU General Public License v3',
    url='https://github.com/s0md3v/wappalyzer-next',
    download_url='https://github.com/s0md3v/wappalyzer-next/archive/1.0.14.zip',
    packages=find_packages(),
    package_data={'wappalyzer': ['data/*']},
    install_requires=[
        'requests',
        'huepy',
        'selenium',
        'tldextract',
        'beautifulsoup4',
        'dnspython'
    ],
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Intended Audience :: Information Technology',
        'Operating System :: OS Independent',
        'Topic :: Security',
        'Programming Language :: Python :: 3.4',
    ],
    entry_points={
        'console_scripts': [
            'wappalyzer = wappalyzer.__main__:main'
        ]
    },
    keywords=['wappalyzer', 'tech stack', 'bug bounty', 'pentesting', 'security', 'whatruns'],
)
