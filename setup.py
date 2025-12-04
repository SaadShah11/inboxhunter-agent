"""
InboxHunter Agent - Setup Script
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text() if readme_path.exists() else ""

setup(
    name="inboxhunter-agent",
    version="2.0.0",
    author="InboxHunter",
    author_email="support@inboxhunter.io",
    description="Desktop agent for InboxHunter browser automation platform",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/inboxhunter/agent",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "playwright>=1.40.0",
        "playwright-stealth>=2.0.0",
        "httpx>=0.25.0",
        "websockets>=12.0",
        "pystray>=0.19.0",
        "Pillow>=10.0.0",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "pyyaml>=6.0",
        "loguru>=0.7.0",
        "openai>=1.0.0",
        "2captcha-python>=1.2.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.23.0",
            "black>=24.0.0",
            "flake8>=7.0.0",
            "mypy>=1.8.0",
            "pyinstaller>=6.0.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "inboxhunter-agent=main:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Desktop Environment",
        "Intended Audience :: End Users/Desktop",
        "License :: Other/Proprietary License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Internet :: WWW/HTTP :: Browsers",
    ],
    keywords="browser automation, web scraping, email signup",
    project_urls={
        "Documentation": "https://docs.inboxhunter.io",
        "Dashboard": "https://app.inboxhunter.io",
    },
)
