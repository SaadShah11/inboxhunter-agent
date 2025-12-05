# InboxHunter Agent

<p align="center">
  <img src="assets/icon_source.png" alt="InboxHunter Agent" width="128" height="128">
</p>

<p align="center">
  <strong>AI-Powered Browser Automation for Email List Signups</strong>
</p>

<p align="center">
  <a href="#installation">Installation</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#configuration">Configuration</a> •
  <a href="#development">Development</a> •
  <a href="#building">Building</a>
</p>

---

## Overview

The InboxHunter Agent is a desktop application that connects to the InboxHunter platform and executes browser automation tasks. It uses:

- **GPT-4o Vision** for intelligent form detection and filling
- **Playwright** for robust browser automation with stealth features
- **2Captcha** for automatic CAPTCHA solving
- **Socket.IO** for real-time communication with the platform

## Installation

### Pre-built Installers (Recommended)

Download the latest installer for your platform from the [Dashboard](https://app.inboxhunter.io/dashboard/download) or [GitHub Releases](https://github.com/YOUR_ORG/inboxhunter-agent/releases).

| Platform | Download |
|----------|----------|
| **Windows** | `InboxHunterAgent-Setup.exe` |
| **macOS** | `InboxHunterAgent.dmg` |
| **Linux** | `InboxHunterAgent.AppImage` |

#### Windows

1. Download the `.exe` installer
2. Run the installer and follow the setup wizard
3. Launch "InboxHunter Agent" from your desktop or Start Menu

#### macOS

1. Download the `.dmg` file
2. Open the DMG and drag the app to Applications
3. Right-click → Open (first time only, to bypass Gatekeeper)
4. If blocked, go to System Preferences → Security & Privacy → Allow

#### Linux

```bash
# Download the AppImage
wget https://github.com/YOUR_ORG/inboxhunter-agent/releases/latest/download/InboxHunterAgent.AppImage

# Make it executable
chmod +x InboxHunterAgent.AppImage

# Run it
./InboxHunterAgent.AppImage
```

### From Source (Development)

```bash
# Clone the repository
git clone https://github.com/YOUR_ORG/inboxhunter-agent.git
cd inboxhunter-agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Run the agent
python main.py --console --debug
```

## Quick Start

### 1. Get a Registration Token

1. Log in to the [InboxHunter Dashboard](https://app.inboxhunter.io)
2. Go to **Dashboard → Download Agent**
3. Click **"Generate Registration Token"**
4. Copy the token

### 2. Register the Agent

```bash
# Run with --register flag
./InboxHunterAgent --register

# Or in development:
python main.py --register
```

Enter your registration token when prompted.

### 3. Configure API Keys

Edit `config/config.yaml`:

```yaml
llm:
  provider: "openai"
  api_key: "sk-your-openai-api-key"  # Required for form detection
  model: "gpt-4o"

captcha:
  service: "2captcha"
  api_key: "your-2captcha-key"  # Optional, for CAPTCHA solving
```

### 4. Start the Agent

```bash
# Normal mode (system tray)
./InboxHunterAgent

# Console mode (see logs)
./InboxHunterAgent --console

# Debug mode (verbose logging)
./InboxHunterAgent --console --debug
```

The agent will appear in your system tray and automatically connect to the platform.

## Configuration

### Configuration File (`config/config.yaml`)

```yaml
# Platform Connection
platform:
  api_url: "https://api.inboxhunter.io"
  ws_url: "wss://api.inboxhunter.io/ws/agent"

# Credentials for form filling
credentials:
  first_name: "John"
  last_name: "Doe"
  email: "john@example.com"
  phone:
    country_code: "+1"
    number: "5551234567"

# LLM Configuration (Required)
llm:
  enabled: true
  provider: "openai"
  api_key: "sk-your-openai-api-key"
  model: "gpt-4o"  # Recommended for vision

# CAPTCHA Solving (Optional)
captcha:
  service: "2captcha"
  api_key: "your-2captcha-api-key"
  timeout: 120

# Browser Settings
automation:
  browser: "chromium"
  headless: false  # Set true to hide browser
  viewport_width: 1920
  viewport_height: 1080
  stealth_enabled: true

# Rate Limiting
rate_limiting:
  max_signups_per_hour: 25
  max_signups_per_day: 250
  delay_between_signups: [30, 90]  # Random delay range
```

### Environment Variables

You can also use environment variables:

```bash
export OPENAI_API_KEY="sk-..."
export TWOCAPTCHA_API_KEY="..."
export INBOXHUNTER_API_URL="https://api.inboxhunter.io"
```

### Command Line Options

```
Usage: InboxHunterAgent [OPTIONS]

Options:
  --register      Register agent with platform
  --console       Run in console mode (no system tray)
  --debug         Enable debug logging
  --version       Show version and exit
  --help          Show this help message
```

## How It Works

### Task Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Platform     │────▶│     Agent       │────▶│    Browser      │
│   (Dashboard)   │     │  (Your Machine) │     │  (Automated)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        │  1. Dispatch Task     │                       │
        │──────────────────────▶│                       │
        │                       │  2. Navigate to URL   │
        │                       │──────────────────────▶│
        │                       │  3. Analyze with GPT  │
        │                       │──────────────────────▶│
        │                       │  4. Fill Form         │
        │                       │──────────────────────▶│
        │  5. Report Results    │                       │
        │◀──────────────────────│                       │
```

### AI Form Detection

The agent uses GPT-4o Vision to:

1. **Screenshot** the page
2. **Analyze** form structure and fields
3. **Identify** input types (email, name, phone)
4. **Generate** fill actions
5. **Validate** submissions

### Stealth Features

Built-in anti-detection:

- Randomized user agents and screen sizes
- WebGL and canvas fingerprint spoofing
- Human-like typing with variable delays
- Natural mouse movements
- Timezone and locale spoofing

## Development

### Project Structure

```
inboxhunter-agent/
├── main.py                 # Entry point
├── requirements.txt        # Python dependencies
├── build.py               # Build script
├── config/
│   ├── config.example.yaml # Example configuration
│   └── config.yaml        # Your configuration
├── assets/
│   ├── icon.ico           # Windows icon
│   ├── icon.icns          # macOS icon
│   └── icon.png           # Linux icon
└── src/
    ├── core/
    │   ├── agent.py       # Main agent controller
    │   ├── config.py      # Configuration management
    │   └── updater.py     # Auto-update system
    ├── api/
    │   ├── client.py      # REST API client
    │   └── websocket.py   # Socket.IO client
    ├── automation/
    │   ├── browser.py     # Browser automation
    │   ├── agent_orchestrator.py  # AI agent loop
    │   └── llm_analyzer.py        # GPT-4o integration
    ├── captcha/
    │   └── solver.py      # CAPTCHA solving
    ├── scrapers/
    │   └── meta_ads.py    # Meta Ads Library scraper
    └── ui/
        └── tray.py        # System tray UI
```

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest tests/
```

### Code Style

```bash
# Format code
pip install black isort
black .
isort .

# Lint
pip install flake8
flake8 src/
```

## Building

### Generate Icons

```bash
# Install Pillow
pip install Pillow

# Generate icons for all platforms
python assets/generate_icons.py

# Or provide a custom source image
python assets/generate_icons.py path/to/logo.png
```

### Build Executable

```bash
# Build for current platform
python build.py

# Build without bundled browser (smaller)
python build.py --no-browser

# Build with console (for debugging)
python build.py --debug
```

Output will be in `dist/`:

- **Windows**: `InboxHunterAgent.exe`
- **macOS**: `InboxHunterAgent.app` + `InboxHunterAgent.dmg`
- **Linux**: `InboxHunterAgent` + `InboxHunterAgent.AppImage`

### Automated Builds

The GitHub Actions workflow automatically builds for all platforms when you:

1. Push a tag: `git tag agent-v2.1.0 && git push --tags`
2. Or manually trigger the workflow

## Troubleshooting

### Agent Won't Connect

1. Check your registration token hasn't expired (valid for 1 hour)
2. Verify the platform URL is correct
3. Check firewall settings allow WebSocket connections
4. Run with `--debug` to see detailed logs

### Form Detection Fails

1. Ensure your OpenAI API key is valid and has GPT-4o access
2. Check if the page has unusual anti-bot protection
3. Try running with `headless: false` to see what's happening
4. Check the logs for specific error messages

### Browser Crashes

1. Update Playwright: `pip install -U playwright && playwright install`
2. Clear browser cache: Delete `~/.cache/ms-playwright`
3. Try a different browser in config: `browser: "firefox"`

### CAPTCHA Issues

1. Verify your 2Captcha API key and balance
2. Increase timeout in config if CAPTCHAs are complex
3. Check 2Captcha service status

## Auto-Updates

The agent automatically checks for updates on startup. When an update is available:

1. You'll see a notification in the system tray
2. Choose "Update Now" to download and install
3. The agent will restart automatically

To disable auto-updates:

```yaml
agent:
  check_updates: false
```

## Support

- **Issues**: [GitHub Issues](https://github.com/YOUR_ORG/inboxhunter-agent/issues)
- **Documentation**: [docs.inboxhunter.io](https://docs.inboxhunter.io)
- **Email**: support@inboxhunter.io

## License

This project is proprietary software. See [LICENSE](LICENSE) for details.

---

<p align="center">
  Made with ❤️ by the InboxHunter Team
</p>
