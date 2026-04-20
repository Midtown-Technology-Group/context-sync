"""Work Context Sync - Package setup

Team distribution package for Microsoft 365 context sync tool.
"""
from pathlib import Path
from setuptools import setup, find_packages

README = Path(__file__).parent / "README.md"
long_description = README.read_text(encoding="utf-8") if README.exists() else ""

setup(
    name="mtg-work-context-sync",
    version="1.1.0",
    description="Sync Microsoft 365 work context to LogSeq knowledge graph",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Thomas Bray",
    author_email="thomas@midtowntg.com",
    url="https://github.com/midtowntg/work-context-sync",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.10",
    install_requires=[
        "msal>=1.29",
        "pydantic>=2.0",
        "requests>=2.28",
    ],
    extras_require={
        "windows": [
            "msal_extensions>=1.0",  # Required for DPAPI encryption
        ],
        "dev": [
            "pytest>=7.0",
            "pytest-asyncio",
            "black",
            "mypy",
        ],
    },
    entry_points={
        "console_scripts": [
            "work-context-sync=work_context_sync.app:main",
            "wcsync=work_context_sync.app:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Information Technology",
        "Topic :: Office/Business :: Scheduling",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX :: Linux",
    ],
    keywords="microsoft365, graph-api, logseq, gtd, productivity",
    project_urls={
        "Bug Reports": "https://github.com/midtowntg/work-context-sync/issues",
        "Source": "https://github.com/midtowntg/work-context-sync",
        "Documentation": "https://github.com/midtowntg/work-context-sync/wiki",
    },
    include_package_data=True,
    package_data={
        "work_context_sync": ["py.typed"],
    },
    zip_safe=False,
)
