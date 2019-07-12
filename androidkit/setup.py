#!/usr/bin/env python

from distutils.core import setup

setup(name='androidkit',
      version='1.0',
      description='Functions used on android',
      author='Seonghoi Lee',
      author_email='mighty1231@kaist.ac.kr',
      packages=['androidkit'],
      package_data={'androidkit': ['sdcard/*']}
     )
