from setuptools import setup, find_packages

setup(
    version="0.2.5",
    packages=find_packages(),
    install_requires=[
        "requests",
        "pendulum",
        "retrying",
        "notion-client",
        "Pillow",
        "Pillow",
    ],
    entry_points={
        "console_scripts": [
            "book = weread2notionpro.book:main",
            "weread = weread2notionpro.weread:main",
            "read_time = weread2notionpro.read_time:main",
        ],
    },
    author="oioi",
    author_email="oioi@users.noreply.github.com",
    description="自动将微信读书笔记和阅读记录同步到Notion",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/oioilu/weread2notion-pro",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)
