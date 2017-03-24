from setuptools import setup

setup(
    name='bmfg',
    py_modules=['bmfg'],
    entry_points={
        'console_scripts': ['bmfg = bmfg:main', ],
    },
)
