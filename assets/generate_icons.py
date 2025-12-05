#!/usr/bin/env python3
"""
Generate app icons for all platforms from a source image.

Usage:
    pip install Pillow cairosvg
    
    # Auto-detect source image in assets folder
    python generate_icons.py
    
    # Or specify a source image
    python generate_icons.py path/to/logo.png

Supported source formats: PNG, JPG, JPEG, SVG, WEBP, BMP, TIFF

The script will look for source images in this order:
1. Command line argument
2. logo.png, logo.svg, icon_source.png, source.png in assets folder
3. Generate a default placeholder icon
"""

import os
import sys
from pathlib import Path
from typing import Optional

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Installing Pillow...")
    os.system(f"{sys.executable} -m pip install Pillow")
    from PIL import Image, ImageDraw


ASSETS_DIR = Path(__file__).parent

# Source image names to look for (in order of priority)
SOURCE_IMAGE_NAMES = [
    "logo.png",
    "logo.svg", 
    "logo.jpg",
    "logo.jpeg",
    "icon_source.png",
    "source.png",
    "source.svg",
    "app_icon.png",
    "InboxHunter*.png",  # Glob pattern
]

ICON_SIZES = {
    "windows": [16, 24, 32, 48, 64, 128, 256],
    "macos": [16, 32, 64, 128, 256, 512, 1024],
    "linux": [16, 24, 32, 48, 64, 128, 256, 512],
}


def find_source_image() -> Optional[Path]:
    """Find a source image in the assets directory."""
    print("🔍 Looking for source image in assets folder...")
    
    for pattern in SOURCE_IMAGE_NAMES:
        if "*" in pattern:
            # Handle glob patterns
            matches = list(ASSETS_DIR.glob(pattern))
            if matches:
                print(f"   Found: {matches[0].name}")
                return matches[0]
        else:
            path = ASSETS_DIR / pattern
            if path.exists():
                print(f"   Found: {path.name}")
                return path
    
    return None


def load_source_image(source_path: Path) -> Image.Image:
    """Load and prepare source image for icon generation."""
    print(f"📷 Loading source image: {source_path.name}")
    
    suffix = source_path.suffix.lower()
    
    # Handle SVG files
    if suffix == ".svg":
        try:
            import cairosvg
            import io
            
            # Convert SVG to PNG at high resolution
            png_data = cairosvg.svg2png(
                url=str(source_path),
                output_width=1024,
                output_height=1024
            )
            img = Image.open(io.BytesIO(png_data))
            print("   Converted SVG to PNG")
        except ImportError:
            print("   ⚠️ cairosvg not installed, trying alternative method...")
            # Try using Pillow directly (limited SVG support)
            img = Image.open(source_path)
    else:
        img = Image.open(source_path)
    
    # Convert to RGBA for transparency support
    img = img.convert("RGBA")
    
    # Make square if not already (center crop or pad)
    width, height = img.size
    if width != height:
        print(f"   Adjusting aspect ratio ({width}x{height} → square)")
        size = max(width, height)
        new_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        paste_x = (size - width) // 2
        paste_y = (size - height) // 2
        new_img.paste(img, (paste_x, paste_y))
        img = new_img
    
    # Resize to 1024x1024 for best quality
    if img.size != (1024, 1024):
        print(f"   Resizing to 1024x1024")
        img = img.resize((1024, 1024), Image.Resampling.LANCZOS)
    
    return img


def create_default_icon(size: int = 1024) -> Image.Image:
    """Create a default InboxHunter icon if no source is provided."""
    print("📦 Generating default placeholder icon...")
    
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw rounded rectangle background
    padding = size // 16
    radius = size // 5
    
    # Indigo gradient-like background
    draw.rounded_rectangle(
        [padding, padding, size - padding, size - padding],
        radius=radius,
        fill=(79, 70, 229)  # Indigo-600
    )
    
    # Draw envelope icon
    envelope_margin = size // 4
    env_left = envelope_margin
    env_right = size - envelope_margin
    env_top = size // 3
    env_bottom = size - size // 3
    
    # Envelope body
    draw.rounded_rectangle(
        [env_left, env_top, env_right, env_bottom],
        radius=size // 20,
        fill=(255, 255, 255)
    )
    
    # Envelope flap (triangle)
    center_x = size // 2
    flap_points = [
        (env_left, env_top),
        (center_x, env_top + (env_bottom - env_top) // 2),
        (env_right, env_top)
    ]
    draw.polygon(flap_points, fill=(255, 255, 255))
    
    # Inbox arrow
    arrow_color = (79, 70, 229)
    arrow_size = size // 8
    arrow_center_y = env_top - arrow_size
    arrow_points = [
        (center_x, arrow_center_y + arrow_size),
        (center_x - arrow_size // 2, arrow_center_y),
        (center_x + arrow_size // 2, arrow_center_y),
    ]
    draw.polygon(arrow_points, fill=arrow_color)
    
    # Arrow stem
    stem_width = arrow_size // 3
    draw.rectangle(
        [center_x - stem_width // 2, arrow_center_y - arrow_size // 2,
         center_x + stem_width // 2, arrow_center_y],
        fill=arrow_color
    )
    
    return img


def create_ico(source: Image.Image, output_path: Path):
    """Create Windows .ico file with multiple sizes."""
    sizes = [(s, s) for s in ICON_SIZES["windows"]]
    images = [source.resize(size, Image.Resampling.LANCZOS) for size in sizes]
    images[0].save(output_path, format="ICO", sizes=sizes)
    print(f"   ✅ {output_path.name}")


def create_icns(source: Image.Image, output_path: Path):
    """Create macOS .icns file."""
    try:
        # Try using iconutil (macOS only)
        import subprocess
        import tempfile
        
        iconset_dir = Path(tempfile.mkdtemp()) / "icon.iconset"
        iconset_dir.mkdir()
        
        # Generate all required sizes for macOS
        icns_sizes = [
            (16, "16x16"),
            (32, "16x16@2x"),
            (32, "32x32"),
            (64, "32x32@2x"),
            (128, "128x128"),
            (256, "128x128@2x"),
            (256, "256x256"),
            (512, "256x256@2x"),
            (512, "512x512"),
            (1024, "512x512@2x"),
        ]
        
        for size, name in icns_sizes:
            resized = source.resize((size, size), Image.Resampling.LANCZOS)
            resized.save(iconset_dir / f"icon_{name}.png")
        
        # Convert to icns using iconutil
        result = subprocess.run(
            ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(output_path)],
            check=True,
            capture_output=True
        )
        print(f"   ✅ {output_path.name}")
        
        # Cleanup
        import shutil
        shutil.rmtree(iconset_dir.parent)
        
    except FileNotFoundError:
        print(f"   ⚠️ iconutil not found (not on macOS), creating PNG fallback")
        source.save(output_path.with_suffix(".png"))
        print(f"   ✅ {output_path.with_suffix('.png').name} (PNG fallback)")
    except Exception as e:
        print(f"   ⚠️ Could not create .icns: {e}")
        source.save(output_path.with_suffix(".png"))
        print(f"   ✅ {output_path.with_suffix('.png').name} (PNG fallback)")


def create_png(source: Image.Image, output_path: Path, size: int = 512):
    """Create PNG icon at specified size."""
    resized = source.resize((size, size), Image.Resampling.LANCZOS)
    resized.save(output_path, format="PNG")
    print(f"   ✅ {output_path.name}")


def main():
    print("\n" + "=" * 50)
    print("🎨 InboxHunter Icon Generator")
    print("=" * 50 + "\n")
    
    # Determine source image
    source_path = None
    
    if len(sys.argv) > 1:
        # Use command line argument
        source_path = Path(sys.argv[1])
        if not source_path.exists():
            print(f"❌ Source file not found: {source_path}")
            sys.exit(1)
    else:
        # Auto-detect source image
        source_path = find_source_image()
    
    # Load or create source image
    if source_path:
        source = load_source_image(source_path)
    else:
        print("   No source image found in assets folder")
        print("   💡 Tip: Add logo.png to the assets folder")
        source = create_default_icon(1024)
    
    # Save source as reference
    source.save(ASSETS_DIR / "icon_source.png")
    print(f"\n📁 Saved processed source: icon_source.png")
    
    # Create Windows icon
    print("\n🪟 Creating Windows icon (.ico)...")
    create_ico(source, ASSETS_DIR / "icon.ico")
    
    # Create macOS icon
    print("\n🍎 Creating macOS icon (.icns)...")
    create_icns(source, ASSETS_DIR / "icon.icns")
    
    # Create Linux icon
    print("\n🐧 Creating Linux icons (.png)...")
    create_png(source, ASSETS_DIR / "icon.png", 512)
    
    # Create additional sizes for Linux desktop integration
    linux_icons_dir = ASSETS_DIR / "linux"
    linux_icons_dir.mkdir(exist_ok=True)
    
    for size in ICON_SIZES["linux"]:
        create_png(source, linux_icons_dir / f"icon_{size}x{size}.png", size)
    
    print("\n" + "=" * 50)
    print("✅ All icons generated successfully!")
    print(f"📁 Output directory: {ASSETS_DIR}")
    print("=" * 50 + "\n")
    
    print("Generated files:")
    print("  • icon.ico       (Windows)")
    print("  • icon.icns      (macOS)")
    print("  • icon.png       (Linux/General)")
    print("  • linux/         (Various sizes for Linux)")
    print()


if __name__ == "__main__":
    main()
