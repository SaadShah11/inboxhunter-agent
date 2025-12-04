"""
Helper functions for the bot.
"""

import random
import time
import math
from typing import Tuple, List


def random_delay(min_seconds: float, max_seconds: float) -> float:
    """
    Generate a random delay between min and max seconds.
    
    Args:
        min_seconds: Minimum delay in seconds
        max_seconds: Maximum delay in seconds
        
    Returns:
        Random delay value
    """
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)
    return delay


def human_typing_delay() -> float:
    """
    Generate a human-like typing delay.
    Uses a normal distribution to simulate realistic typing speeds.
    
    Returns:
        Delay in seconds
    """
    # Average typing speed: ~40-60 WPM = ~0.1-0.15s per character
    # Use normal distribution for more realistic timing
    delay = random.gauss(0.15, 0.05)
    # Ensure delay is positive and reasonable
    delay = max(0.05, min(0.5, delay))
    return delay


def generate_realistic_mouse_path(
    start: Tuple[float, float],
    end: Tuple[float, float],
    steps: int = 10
) -> List[Tuple[float, float]]:
    """
    Generate a realistic mouse movement path from start to end.
    Uses Bezier curves for natural movement.
    
    Args:
        start: Starting (x, y) coordinates
        end: Ending (x, y) coordinates
        steps: Number of intermediate points
        
    Returns:
        List of (x, y) coordinates forming the path
    """
    # Generate control points for Bezier curve
    # Add some randomness to make it look more natural
    mid_x = (start[0] + end[0]) / 2 + random.uniform(-50, 50)
    mid_y = (start[1] + end[1]) / 2 + random.uniform(-50, 50)
    
    control1 = (
        start[0] + (mid_x - start[0]) * 0.33,
        start[1] + (mid_y - start[1]) * 0.33
    )
    control2 = (
        start[0] + (mid_x - start[0]) * 0.66,
        start[1] + (mid_y - start[1]) * 0.66
    )
    
    # Generate points along the Bezier curve
    path = []
    for i in range(steps + 1):
        t = i / steps
        
        # Cubic Bezier curve formula
        x = (
            (1 - t) ** 3 * start[0] +
            3 * (1 - t) ** 2 * t * control1[0] +
            3 * (1 - t) * t ** 2 * control2[0] +
            t ** 3 * end[0]
        )
        y = (
            (1 - t) ** 3 * start[1] +
            3 * (1 - t) ** 2 * t * control1[1] +
            3 * (1 - t) * t ** 2 * control2[1] +
            t ** 3 * end[1]
        )
        
        # Add slight randomness to each point
        x += random.uniform(-2, 2)
        y += random.uniform(-2, 2)
        
        path.append((x, y))
    
    return path


def calculate_distance(point1: Tuple[float, float], point2: Tuple[float, float]) -> float:
    """Calculate Euclidean distance between two points."""
    return math.sqrt((point2[0] - point1[0]) ** 2 + (point2[1] - point1[1]) ** 2)


def should_make_typo(probability: float = 0.05) -> bool:
    """
    Determine if a typing mistake should be made.
    
    Args:
        probability: Probability of making a typo (0.0 to 1.0)
        
    Returns:
        True if a typo should be made
    """
    return random.random() < probability


def get_adjacent_key(char: str) -> str:
    """
    Get an adjacent key on a QWERTY keyboard for simulating typos.
    
    Args:
        char: Original character
        
    Returns:
        Adjacent character or original if no mapping exists
    """
    keyboard_map = {
        'a': ['q', 's', 'z'],
        'b': ['v', 'g', 'h', 'n'],
        'c': ['x', 'd', 'f', 'v'],
        'd': ['s', 'e', 'r', 'f', 'c', 'x'],
        'e': ['w', 'r', 'd', 's'],
        'f': ['d', 'r', 't', 'g', 'v', 'c'],
        'g': ['f', 't', 'y', 'h', 'b', 'v'],
        'h': ['g', 'y', 'u', 'j', 'n', 'b'],
        'i': ['u', 'o', 'k', 'j'],
        'j': ['h', 'u', 'i', 'k', 'm', 'n'],
        'k': ['j', 'i', 'o', 'l', 'm'],
        'l': ['k', 'o', 'p'],
        'm': ['n', 'j', 'k'],
        'n': ['b', 'h', 'j', 'm'],
        'o': ['i', 'p', 'l', 'k'],
        'p': ['o', 'l'],
        'q': ['w', 'a'],
        'r': ['e', 't', 'f', 'd'],
        's': ['a', 'w', 'e', 'd', 'x', 'z'],
        't': ['r', 'y', 'g', 'f'],
        'u': ['y', 'i', 'j', 'h'],
        'v': ['c', 'f', 'g', 'b'],
        'w': ['q', 'e', 's', 'a'],
        'x': ['z', 's', 'd', 'c'],
        'y': ['t', 'u', 'h', 'g'],
        'z': ['a', 's', 'x']
    }
    
    char_lower = char.lower()
    if char_lower in keyboard_map:
        adjacent = random.choice(keyboard_map[char_lower])
        return adjacent.upper() if char.isupper() else adjacent
    return char


def format_phone_number(phone: str) -> str:
    """
    Format phone number to remove special characters.
    
    Args:
        phone: Phone number with possible special characters
        
    Returns:
        Cleaned phone number
    """
    return ''.join(filter(str.isdigit, phone))


def is_valid_email(email: str) -> bool:
    """
    Simple email validation.
    
    Args:
        email: Email address to validate
        
    Returns:
        True if email appears valid
    """
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

