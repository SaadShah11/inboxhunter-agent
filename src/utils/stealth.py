"""
Advanced stealth utilities for browser automation.
Implements user agent rotation, fingerprint randomization, and modern anti-detection.
"""

import random
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from loguru import logger


@dataclass
class BrowserProfile:
    """Represents a complete browser fingerprint profile."""
    user_agent: str
    platform: str
    vendor: str
    renderer: str
    webgl_vendor: str
    timezone: str
    language: str
    screen_resolution: tuple
    color_depth: int
    device_memory: int
    hardware_concurrency: int


# Modern user agents (updated for 2024-2025)
USER_AGENTS = {
    "chrome_windows": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    ],
    "chrome_mac": [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    ],
    "edge_windows": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
    ],
    "firefox_windows": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    ],
    "firefox_mac": [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.0; rv:133.0) Gecko/20100101 Firefox/133.0",
    ],
    "safari_mac": [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
    ],
}

# Screen resolutions with popularity weights
SCREEN_RESOLUTIONS = [
    ((1920, 1080), 35),  # Most common
    ((2560, 1440), 20),
    ((1366, 768), 15),
    ((1536, 864), 10),
    ((1440, 900), 8),
    ((1680, 1050), 5),
    ((3840, 2160), 4),  # 4K
    ((2560, 1080), 3),  # Ultrawide
]

# Timezones with approximate usage
TIMEZONES = [
    ("America/New_York", 25),
    ("America/Los_Angeles", 15),
    ("America/Chicago", 12),
    ("America/Denver", 5),
    ("Europe/London", 10),
    ("Europe/Paris", 5),
    ("Australia/Sydney", 3),
    ("Asia/Tokyo", 3),
]

# WebGL renderers for different platforms
WEBGL_CONFIGS = {
    "windows": [
        ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 6700 XT Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) UHD Graphics 770 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ],
    "mac": [
        ("Apple Inc.", "Apple M1"),
        ("Apple Inc.", "Apple M2"),
        ("Apple Inc.", "Apple M3"),
        ("Intel Inc.", "Intel Iris Plus Graphics 655"),
    ],
}


def weighted_choice(choices: List[tuple]) -> Any:
    """Select from weighted choices."""
    total = sum(weight for _, weight in choices)
    r = random.uniform(0, total)
    cumulative = 0
    for choice, weight in choices:
        cumulative += weight
        if r <= cumulative:
            return choice
    return choices[-1][0]


def get_random_user_agent(browser_type: str = "chrome", platform: str = "random") -> str:
    """
    Get a random modern user agent.
    
    Args:
        browser_type: 'chrome', 'firefox', 'edge', 'safari', or 'random'
        platform: 'windows', 'mac', or 'random'
    """
    if platform == "random":
        platform = random.choices(["windows", "mac"], weights=[70, 30])[0]
    
    if browser_type == "random":
        if platform == "windows":
            browser_type = random.choices(["chrome", "edge", "firefox"], weights=[70, 20, 10])[0]
        else:
            browser_type = random.choices(["chrome", "safari", "firefox"], weights=[60, 30, 10])[0]
    
    key = f"{browser_type}_{platform}"
    if key in USER_AGENTS:
        return random.choice(USER_AGENTS[key])
    
    # Fallback to Chrome Windows
    return random.choice(USER_AGENTS["chrome_windows"])


def generate_browser_profile(prefer_platform: str = "random") -> BrowserProfile:
    """
    Generate a complete, consistent browser fingerprint profile.
    """
    platform = prefer_platform if prefer_platform != "random" else random.choices(["windows", "mac"], weights=[70, 30])[0]
    
    user_agent = get_random_user_agent(browser_type="chrome", platform=platform)
    screen_res = weighted_choice(SCREEN_RESOLUTIONS)
    timezone = weighted_choice(TIMEZONES)
    
    webgl_config = random.choice(WEBGL_CONFIGS.get(platform, WEBGL_CONFIGS["windows"]))
    
    return BrowserProfile(
        user_agent=user_agent,
        platform="Win32" if platform == "windows" else "MacIntel",
        vendor="Google Inc.",
        renderer="WebKit",
        webgl_vendor=webgl_config[0],
        timezone=timezone,
        language="en-US",
        screen_resolution=screen_res,
        color_depth=24,
        device_memory=random.choice([4, 8, 16, 32]),
        hardware_concurrency=random.choice([4, 8, 12, 16]),
    )


def get_stealth_scripts(profile: BrowserProfile) -> str:
    """
    Generate comprehensive stealth scripts for the given profile.
    These scripts patch browser APIs to avoid detection.
    """
    return f"""
    // ============================================
    // ADVANCED STEALTH SCRIPTS
    // ============================================
    
    // 1. Remove webdriver property
    Object.defineProperty(navigator, 'webdriver', {{
        get: () => undefined,
        configurable: true
    }});
    delete navigator.__proto__.webdriver;
    
    // 2. Fix navigator properties
    Object.defineProperties(navigator, {{
        platform: {{ get: () => '{profile.platform}' }},
        vendor: {{ get: () => '{profile.vendor}' }},
        languages: {{ get: () => ['en-US', 'en'] }},
        deviceMemory: {{ get: () => {profile.device_memory} }},
        hardwareConcurrency: {{ get: () => {profile.hardware_concurrency} }},
    }});
    
    // 3. Chrome runtime (required for many checks)
    if (!window.chrome) {{
        window.chrome = {{
            runtime: {{
                connect: () => {{}},
                sendMessage: () => {{}},
                onMessage: {{ addListener: () => {{}} }},
            }},
            loadTimes: () => ({{}}),
            csi: () => ({{}}),
        }};
    }}
    
    // 4. Plugins - mimic real Chrome
    Object.defineProperty(navigator, 'plugins', {{
        get: () => {{
            const plugins = [
                {{ name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }},
                {{ name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' }},
                {{ name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }},
            ];
            plugins.item = (i) => plugins[i];
            plugins.namedItem = (name) => plugins.find(p => p.name === name);
            plugins.refresh = () => {{}};
            return plugins;
        }}
    }});
    
    // 5. Permissions API
    const originalQuery = window.navigator.permissions?.query;
    if (originalQuery) {{
        window.navigator.permissions.query = (parameters) => {{
            if (parameters.name === 'notifications') {{
                return Promise.resolve({{ state: Notification.permission, onchange: null }});
            }}
            return originalQuery.call(navigator.permissions, parameters);
        }};
    }}
    
    // 6. WebGL fingerprint
    const getParameterProto = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {{
        if (parameter === 37445) return '{profile.webgl_vendor}';
        if (parameter === 37446) return '{profile.webgl_vendor}';
        return getParameterProto.call(this, parameter);
    }};
    
    const getParameter2Proto = WebGL2RenderingContext?.prototype?.getParameter;
    if (getParameter2Proto) {{
        WebGL2RenderingContext.prototype.getParameter = function(parameter) {{
            if (parameter === 37445) return '{profile.webgl_vendor}';
            if (parameter === 37446) return '{profile.webgl_vendor}';
            return getParameter2Proto.call(this, parameter);
        }};
    }}
    
    // 7. Screen properties
    Object.defineProperties(screen, {{
        width: {{ get: () => {profile.screen_resolution[0]} }},
        height: {{ get: () => {profile.screen_resolution[1]} }},
        availWidth: {{ get: () => {profile.screen_resolution[0]} }},
        availHeight: {{ get: () => {profile.screen_resolution[1] - 40} }},
        colorDepth: {{ get: () => {profile.color_depth} }},
        pixelDepth: {{ get: () => {profile.color_depth} }},
    }});
    
    // 8. Fix outerWidth/Height for headless detection
    Object.defineProperties(window, {{
        outerWidth: {{ get: () => {profile.screen_resolution[0]} }},
        outerHeight: {{ get: () => {profile.screen_resolution[1]} }},
        innerWidth: {{ get: () => {profile.screen_resolution[0] - 10} }},
        innerHeight: {{ get: () => {profile.screen_resolution[1] - 100} }},
    }});
    
    // 9. Remove Playwright/automation markers
    delete window.__playwright;
    delete window.__pw_manual;
    delete window.__PW_inspect;
    
    // 10. Fix toString to return native function strings
    const fakeToString = (fn, str) => {{
        const handler = {{
            apply: function(target, thisArg, args) {{
                if (thisArg === fn) return str;
                return target.apply(thisArg, args);
            }}
        }};
        return new Proxy(Function.prototype.toString, handler);
    }};
    
    // 11. Connection type (for mobile detection)
    Object.defineProperty(navigator, 'connection', {{
        get: () => ({{
            effectiveType: '4g',
            rtt: 50,
            downlink: 10,
            saveData: false,
        }})
    }});
    
    // 12. Battery API (optional, some sites check)
    if (navigator.getBattery) {{
        navigator.getBattery = () => Promise.resolve({{
            charging: true,
            chargingTime: 0,
            dischargingTime: Infinity,
            level: 1,
        }});
    }}
    
    // 13. Media devices (some sites enumerate)
    if (navigator.mediaDevices?.enumerateDevices) {{
        const original = navigator.mediaDevices.enumerateDevices.bind(navigator.mediaDevices);
        navigator.mediaDevices.enumerateDevices = async () => {{
            const devices = await original();
            // Return some fake devices if empty (headless usually has none)
            if (devices.length === 0) {{
                return [
                    {{ deviceId: 'default', kind: 'audioinput', label: '', groupId: 'default' }},
                    {{ deviceId: 'default', kind: 'audiooutput', label: '', groupId: 'default' }},
                    {{ deviceId: 'default', kind: 'videoinput', label: '', groupId: 'default' }},
                ];
            }}
            return devices;
        }};
    }}
    
    console.log('[Stealth] Anti-detection patches applied');
    """


def get_context_options(profile: BrowserProfile, proxy_config: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Get Playwright browser context options with stealth settings.
    """
    options = {
        "viewport": {
            "width": profile.screen_resolution[0],
            "height": profile.screen_resolution[1] - 100,
        },
        "user_agent": profile.user_agent,
        "locale": profile.language,
        "timezone_id": profile.timezone,
        "permissions": ["geolocation"],
        "geolocation": {"latitude": 40.7128, "longitude": -74.0060},  # NYC default
        "color_scheme": random.choice(["light", "dark", "no-preference"]),
        "extra_http_headers": {
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Sec-Ch-Ua": '"Chromium";v="131", "Not_A Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": f'"{profile.platform}"',
            "Cache-Control": "max-age=0",
        },
    }
    
    if proxy_config:
        options["proxy"] = proxy_config
    
    return options


# Create a global profile that persists for the session
_session_profile: Optional[BrowserProfile] = None


def get_session_profile() -> BrowserProfile:
    """Get or create the session's browser profile."""
    global _session_profile
    if _session_profile is None:
        _session_profile = generate_browser_profile()
        logger.info(f"Generated browser profile: {_session_profile.user_agent[:50]}...")
    return _session_profile


def reset_session_profile():
    """Reset the session profile (call between different "sessions")."""
    global _session_profile
    _session_profile = None

