#! /usr/bin/env python3
# -*- coding: utf-8 -*-

from setuptools import setup


setup(
    name='toxdoor',
    version='0.1',
    description='Tox-Core DataBase',
    
    author='Steep Pepper',
    author_email='steephairy@gmail.com',
    url='https://github.com/longnetwork/toxdoor',

    python_requires=">=3.8",

    package_dir={
        'toxdoor': '.',
    },

    packages=['toxdoor', 'toxdoor.toxcore'],
    
    
    install_requires=[
        'requests>=2.32',
    ],

    include_package_data=True,

    package_data={
        'toxdoor': ['toxcore/libtoxcore.so', 'toxcore/libtox.dll', 'bootstrap.txt']
    }

)

