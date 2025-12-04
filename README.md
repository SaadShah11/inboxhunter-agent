# InboxHunter Agent

A lightweight desktop agent that connects to the InboxHunter platform and executes browser automation tasks for email list signups.

## Overview

The InboxHunter Agent is a companion application that runs on your computer and performs the actual browser automation. It connects to the InboxHunter web platform for configuration, task management, and result reporting.

### Key Features

- **System Tray Integration**: Runs quietly in the background
- **Platform Sync**: Receives tasks and settings from web dashboard
- **AI-Powered Forms**: Uses GPT-4o Vision for intelligent form detection
- **Bot Detection Bypass**: Advanced stealth techniques
- **CAPTCHA Solving**: Integrated 2Captcha support
- **Auto Updates**: Automatically keeps itself updated

## Installation

### Option 1: Download Executable (Recommended)

1. Go to [InboxHunter Dashboard](https://app.inboxhunter.io/download)
2. Download the agent for your platform
3. Run the installer
4. Register the agent (see below)

### Option 2: Run from Source

```bash
# Clone the repository
git clone https://github.com/inboxhunter/agent.git
cd agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser
playwright install chromium

# Run the agent
python main.py
```

## Registration

Before using the agent, you need to register it with your InboxHunter account:

1. Log in to [InboxHunter Dashboard](https://app.inboxhunter.io)
2. Go to **Settings → Agents**
3. Click **Add Agent** and copy the registration token
4. Run the agent with registration:
   ```bash
   python main.py --register
   ```
5. Paste the token when prompted

## Usage

### Normal Mode (System Tray)

```bash
python main.py
```

The agent will:
- Appear in your system tray
- Connect to the platform automatically
- Wait for tasks from the dashboard

### Console Mode

```bash
python main.py --console
```

Runs without system tray, useful for servers or debugging.

### Command Line Options

| Option | Description |
|--------|-------------|
| `--register` | Register agent with platform |
| `--console` | Run in console mode |
| `--debug` | Enable debug logging |
| `--version` | Show version |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    InboxHunter Platform                      │
│  (Web Dashboard + API)                                       │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ WebSocket (real-time)
                              │ REST API (config, results)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    InboxHunter Agent                         │
│  ┌─────────┐  ┌─────────────┐  ┌──────────────────────────┐ │
│  │ System  │  │  Platform   │  │    Browser Automation    │ │
│  │  Tray   │  │  Client     │  │  • Playwright            │ │
│  │   UI    │  │  (WS+REST)  │  │  • AI Agent (GPT-4o)     │ │
│  └─────────┘  └─────────────┘  │  • Stealth Mode          │ │
│                                │  • CAPTCHA Solver         │ │
│                                └──────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Project Structure

```
inboxhunter-agent/
├── main.py                 # Entry point
├── src/
│   ├── core/
│   │   ├── agent.py        # Main agent controller
│   │   ├── config.py       # Configuration management
│   │   └── updater.py      # Auto-update mechanism
│   ├── api/
│   │   ├── client.py       # REST API client
│   │   └── websocket.py    # WebSocket client
│   ├── ui/
│   │   └── tray.py         # System tray interface
│   ├── automation/
│   │   ├── browser.py      # Playwright automation
│   │   ├── agent_orchestrator.py  # AI reasoning loop
│   │   └── llm_analyzer.py # GPT-4o Vision integration
│   ├── captcha/
│   │   └── solver.py       # 2Captcha integration
│   └── scrapers/
│       ├── meta_ads.py     # Meta Ads Library scraper
│       └── csv_parser.py   # CSV data source
├── resources/              # Icons and assets
├── config/                 # Configuration files
├── build.py               # Build script
└── requirements.txt
```

## Building from Source

To create a standalone executable:

```bash
# Standard build (with bundled browser, ~300MB)
python build.py

# Without bundled browser (~50MB)
python build.py --no-browser

# Debug build (shows console)
python build.py --debug
```

Output will be in the `dist/` folder.

## Configuration

The agent stores its configuration in:
- **Windows**: `%APPDATA%\InboxHunter\`
- **macOS**: `~/Library/Application Support/InboxHunter/`
- **Linux**: `~/.config/InboxHunter/`

Configuration is automatically synced from the web dashboard.

## Troubleshooting

### Agent won't connect

1. Check your internet connection
2. Verify the agent is registered
3. Check firewall settings for outbound connections
4. Run with `--debug` for more info

### Browser automation fails

1. Make sure Playwright browser is installed:
   ```bash
   playwright install chromium
   ```
2. Try running with `--console` to see errors
3. Check if the target website is blocking automation

### High CPU/Memory usage

1. The agent uses a browser, which requires resources
2. Consider running in headless mode (dashboard setting)
3. Reduce concurrent tasks in dashboard settings

## Development

```bash
# Install dev dependencies
pip install -r requirements.txt

# Run tests
pytest

# Format code
black src/

# Type checking
mypy src/
```

## License

Proprietary - All Rights Reserved

## Support

- **Dashboard**: [app.inboxhunter.io](https://app.inboxhunter.io)
- **Documentation**: [docs.inboxhunter.io](https://docs.inboxhunter.io)
- **Email**: support@inboxhunter.io
