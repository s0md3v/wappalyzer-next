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
    version='2.0.0',
    description='Wappalyzer-based tech stack detection library',
    long_description=desc,
    long_description_content_type='text/markdown',
    author='Somdev Sangwan',
    author_email='s0md3v@gmail.com',
    license='GNU General Public License v3',
    url='https://github.com/s0md3v/wappalyzer-next',
    packages=find_packages(),
    package_data={'wappalyzer': ['data/*']},
    python_requires='>=3.9',
    install_requires=[
        'requests',
        'urllib3',
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
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Programming Language :: Python :: 3.14',
    ],
    entry_points={
        'console_scripts': [
            'wappalyzer = wappalyzer.__main__:main'
        ]
    },
    keywords=['wappalyzer', 'tech stack', 'bug bounty', 'pentesting', 'security', 'whatruns'],
)
