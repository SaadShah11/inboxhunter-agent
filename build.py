#!/usr/bin/env python3
"""
Build script for InboxHunter Agent executable.

Creates a standalone executable with bundled browser for each platform.

Usage:
    python build.py                 # Build for current platform
    python build.py --no-browser    # Build without bundled browser (smaller)
    python build.py --debug         # Build with console window
"""

import os
import sys
import shutil
import subprocess
import platform
from pathlib import Path
from datetime import datetime

# Build configuration
APP_NAME = "InboxHunterAgent"
VERSION = "2.0.0"
MAIN_SCRIPT = "main.py"

# Directories
ROOT_DIR = Path(__file__).parent
BUILD_DIR = ROOT_DIR / "build"
DIST_DIR = ROOT_DIR / "dist"
RESOURCES_DIR = ROOT_DIR / "resources"
ASSETS_DIR = ROOT_DIR / "assets"


def log(message: str, level: str = "INFO"):
    """Print log message."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    symbols = {"INFO": "ℹ️", "SUCCESS": "✅", "WARNING": "⚠️", "ERROR": "❌"}
    symbol = symbols.get(level, "•")
    print(f"[{timestamp}] {symbol} {message}")


def run_command(cmd: list, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return result."""
    log(f"Running: {' '.join(cmd)}")
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def clean_build():
    """Clean previous build artifacts."""
    log("Cleaning previous builds...")
    
    for dir_path in [BUILD_DIR, DIST_DIR]:
        if dir_path.exists():
            shutil.rmtree(dir_path)
            log(f"Removed {dir_path}")
    
    # Remove PyInstaller cache
    cache_dir = ROOT_DIR / "__pycache__"
    if cache_dir.exists():
        shutil.rmtree(cache_dir)


def install_dependencies():
    """Install required dependencies."""
    log("Installing dependencies...")
    
    # Install requirements
    run_command([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    
    # Install PyInstaller if not present
    run_command([sys.executable, "-m", "pip", "install", "pyinstaller"])


def download_browser():
    """Download Playwright browser if needed."""
    log("Checking Playwright browser...")
    
    try:
        result = run_command(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=False
        )
        if result.returncode == 0:
            log("Browser ready", "SUCCESS")
        else:
            log("Browser download may have failed", "WARNING")
    except Exception as e:
        log(f"Browser download error: {e}", "WARNING")


def get_browser_path() -> Path:
    """Get the Playwright browser path."""
    # Try common locations
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    elif platform.system() == "Darwin":
        base = Path.home() / "Library" / "Caches" / "ms-playwright"
    else:
        base = Path.home() / ".cache" / "ms-playwright"
    
    # Find chromium directory
    if base.exists():
        for item in base.iterdir():
            if item.is_dir() and "chromium" in item.name.lower():
                return item
    
    return None


def build_executable(include_browser: bool = True, debug: bool = False):
    """Build the executable with PyInstaller."""
    log(f"Building {APP_NAME} v{VERSION}...")
    
    # Determine platform-specific settings
    system = platform.system()
    
    if system == "Windows":
        exe_name = f"{APP_NAME}.exe"
        icon_ext = ".ico"
        separator = ";"
    elif system == "Darwin":
        exe_name = APP_NAME
        icon_ext = ".icns"
        separator = ":"
    else:
        exe_name = APP_NAME
        icon_ext = ".png"
        separator = ":"
    
    # Build PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--onefile",
        "--clean",
    ]
    
    # Console/windowed mode
    if not debug:
        if system == "Windows":
            cmd.append("--noconsole")
        elif system == "Darwin":
            cmd.append("--windowed")
    
    # Add icon if exists (check assets directory first, then resources)
    icon_path = ASSETS_DIR / f"icon{icon_ext}"
    if not icon_path.exists():
        icon_path = RESOURCES_DIR / f"icon{icon_ext}"
    if icon_path.exists():
        cmd.extend(["--icon", str(icon_path)])
    
    # Hidden imports for dynamic modules
    hidden_imports = [
        # App modules
        "src.core",
        "src.core.agent",
        "src.core.config",
        "src.core.updater",
        "src.api",
        "src.api.client",
        "src.api.websocket",
        "src.ui",
        "src.ui.tray",
        "src.automation",
        "src.automation.agent_orchestrator",
        "src.automation.browser",
        "src.automation.llm_analyzer",
        "src.captcha",
        "src.captcha.solver",
        "src.scrapers",
        "src.scrapers.meta_ads",
        "src.scrapers.csv_parser",
        "src.config",
        # Third-party libraries
        "pystray",
        "PIL",
        "PIL._tkinter_finder",
        "websockets",
        "httpx",
        "openai",
        "socketio",
        "engineio",
        "aiohttp",
        "yaml",
        "pydantic",
        "loguru",
        # Fix for pkg_resources/setuptools issues
        "jaraco",
        "jaraco.text",
        "jaraco.functools",
        "jaraco.context",
        "jaraco.classes",
        "pkg_resources",
        "pkg_resources.extern",
        "setuptools",
        "setuptools._vendor",
        "setuptools._vendor.jaraco",
        "setuptools._vendor.jaraco.text",
        "setuptools._vendor.jaraco.functools",
        "setuptools._vendor.jaraco.context",
        "platformdirs",
        "packaging",
        "packaging.version",
        "packaging.specifiers",
        "packaging.requirements",
        "packaging.markers",
        "importlib_metadata",
        "zipp",
    ]
    
    for imp in hidden_imports:
        cmd.extend(["--hidden-import", imp])
    
    # Exclude problematic modules that cause issues
    excludes = [
        "tkinter",
        "test",
        "unittest",
    ]
    
    for exc in excludes:
        cmd.extend(["--exclude-module", exc])
    
    # Add data files
    data_files = [
        (str(ROOT_DIR / "config" / "config.example.yaml"), "config"),
    ]
    
    if RESOURCES_DIR.exists():
        data_files.append((str(RESOURCES_DIR), "resources"))
    
    for src, dest in data_files:
        if Path(src).exists():
            cmd.extend(["--add-data", f"{src}{separator}{dest}"])
    
    # Add main script
    cmd.append(str(ROOT_DIR / MAIN_SCRIPT))
    
    # Run PyInstaller
    log("Running PyInstaller...")
    result = run_command(cmd, check=False)
    
    if result.returncode != 0:
        log(f"PyInstaller failed: {result.stderr}", "ERROR")
        return False
    
    log(f"Executable built: {DIST_DIR / exe_name}", "SUCCESS")
    
    # Copy browser if requested
    if include_browser:
        copy_browser()
    
    # Create data directory
    create_dist_structure()
    
    return True


def copy_browser():
    """Copy Playwright browser to dist folder."""
    log("Copying browser to dist...")
    
    browser_path = get_browser_path()
    if not browser_path:
        log("Browser path not found, skipping", "WARNING")
        return
    
    dest = DIST_DIR / "browsers" / browser_path.name
    
    try:
        shutil.copytree(browser_path, dest)
        log(f"Browser copied to {dest}", "SUCCESS")
    except Exception as e:
        log(f"Failed to copy browser: {e}", "WARNING")


def create_dist_structure():
    """Create additional directories in dist."""
    log("Creating dist structure...")
    
    # Create directories
    (DIST_DIR / "data").mkdir(exist_ok=True)
    (DIST_DIR / "logs").mkdir(exist_ok=True)
    
    # Create README
    readme_content = f"""# InboxHunter Agent v{VERSION}

## Quick Start

1. Run the agent:
   - Windows: Double-click InboxHunterAgent.exe
   - macOS/Linux: ./InboxHunterAgent

2. Register with platform:
   - Run: ./InboxHunterAgent --register
   - Enter your registration token from the dashboard

3. The agent will appear in your system tray
   - Click to see status and controls
   - Use "Open Dashboard" to manage settings

## Command Line Options

    --register      Register agent with platform
    --console       Run in console mode (no system tray)
    --debug         Enable debug logging
    --version       Show version

## Troubleshooting

- If the agent doesn't start, run with --console to see errors
- Check logs in the data/logs folder
- Make sure you have registered the agent first

## Support

Visit https://app.inboxhunter.io/support for help.
"""
    
    with open(DIST_DIR / "README.txt", "w") as f:
        f.write(readme_content)
    
    # Create launcher script for macOS
    if platform.system() == "Darwin":
        launcher = f"""#!/bin/bash
cd "$(dirname "$0")"
export PLAYWRIGHT_BROWSERS_PATH="$(pwd)/browsers"
./{APP_NAME}
"""
        launcher_path = DIST_DIR / "RunAgent.sh"
        with open(launcher_path, "w") as f:
            f.write(launcher)
        os.chmod(launcher_path, 0o755)
        log("Created launcher script", "SUCCESS")


def main():
    """Main build process."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Build InboxHunter Agent")
    parser.add_argument("--no-browser", action="store_true", help="Don't bundle browser")
    parser.add_argument("--debug", action="store_true", help="Build with console window")
    parser.add_argument("--clean-only", action="store_true", help="Only clean, don't build")
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print(f"Building InboxHunter Agent v{VERSION}")
    print(f"Platform: {platform.system()} {platform.machine()}")
    print(f"{'='*60}\n")
    
    # Change to script directory
    os.chdir(ROOT_DIR)
    
    # Clean
    clean_build()
    
    if args.clean_only:
        log("Clean complete", "SUCCESS")
        return
    
    # Install dependencies
    install_dependencies()
    
    # Download browser
    if not args.no_browser:
        download_browser()
    
    # Build
    success = build_executable(
        include_browser=not args.no_browser,
        debug=args.debug
    )
    
    if success:
        print(f"\n{'='*60}")
        log("Build complete!", "SUCCESS")
        print(f"Output: {DIST_DIR}")
        print(f"{'='*60}\n")
    else:
        print(f"\n{'='*60}")
        log("Build failed!", "ERROR")
        print(f"{'='*60}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()

