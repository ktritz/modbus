#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

from setuptools import setup
import pathlib
import sdist_upip

here = pathlib.Path(__file__).parent.resolve()

# Get the long description from the README file
long_description = (here / 'README.md').read_text(encoding='utf-8')

# load elements of version.py
exec(open(here / 'umodbus' / 'version.py').read())

setup(
    name='micropython-modbus',
    version=__version__,
    description="MicroPython ModBus TCP and RTU library supporting client and host mode",
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/brainelectronics/micropython-modbus',
    author=__author__,
    author_email='info@brainelectronics.de',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
    ],
    keywords='micropython, modbus, tcp, rtu, client, host, library',
    project_urls={
        'Bug Reports': 'https://github.com/brainelectronics/micropython-modbus/issues',
        'Source': 'https://github.com/brainelectronics/micropython-modbus',
    },
    license='MIT',
    cmdclass={'sdist': sdist_upip.sdist},
    packages=['umodbus'],
    install_requires=[]
)
