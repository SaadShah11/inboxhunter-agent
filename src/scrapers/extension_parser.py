"""
Parser for browser extension data (My Ad Finder, Turbo Ad Finder).
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from loguru import logger

from src.config import Config


class ExtensionDataParser:
    """
    Parser for ad data from browser extensions like My Ad Finder and Turbo Ad Finder.
    Supports various data formats (JSON, CSV, etc.).
    """
    
    def __init__(self, config: Config):
        """
        Initialize extension data parser.
        
        Args:
            config: Application configuration
        """
        self.config = config
        self.sources = config.sources
    
    def parse_my_ad_finder(self) -> List[Dict[str, Any]]:
        """
        Parse data from My Ad Finder extension.
        
        Returns:
            List of ad data dictionaries
        """
        if not self.sources.my_ad_finder.enabled:
            logger.warning("My Ad Finder parsing is disabled in config")
            return []
        
        data_path = Path(self.sources.my_ad_finder.data_path)
        
        if not data_path.exists():
            logger.warning(f"My Ad Finder data file not found: {data_path}")
            return []
        
        logger.info(f"Parsing My Ad Finder data from: {data_path}")
        
        try:
            ads = self._parse_json_file(data_path, "my_ad_finder")
            logger.success(f"✅ Parsed {len(ads)} ads from My Ad Finder")
            return ads
        except Exception as e:
            logger.error(f"Error parsing My Ad Finder data: {e}")
            return []
    
    def parse_turbo_ad_finder(self) -> List[Dict[str, Any]]:
        """
        Parse data from Turbo Ad Finder extension.
        
        Returns:
            List of ad data dictionaries
        """
        if not self.sources.turbo_ad_finder.enabled:
            logger.warning("Turbo Ad Finder parsing is disabled in config")
            return []
        
        data_path = Path(self.sources.turbo_ad_finder.data_path)
        
        if not data_path.exists():
            logger.warning(f"Turbo Ad Finder data file not found: {data_path}")
            return []
        
        logger.info(f"Parsing Turbo Ad Finder data from: {data_path}")
        
        try:
            ads = self._parse_json_file(data_path, "turbo_ad_finder")
            logger.success(f"✅ Parsed {len(ads)} ads from Turbo Ad Finder")
            return ads
        except Exception as e:
            logger.error(f"Error parsing Turbo Ad Finder data: {e}")
            return []
    
    def parse_all(self) -> List[Dict[str, Any]]:
        """
        Parse data from all enabled extension sources.
        
        Returns:
            Combined list of ad data from all sources
        """
        all_ads = []
        
        # Parse My Ad Finder
        all_ads.extend(self.parse_my_ad_finder())
        
        # Parse Turbo Ad Finder
        all_ads.extend(self.parse_turbo_ad_finder())
        
        # Remove duplicates
        unique_ads = self._deduplicate_ads(all_ads)
        
        logger.success(f"✅ Total unique ads from extensions: {len(unique_ads)}")
        return unique_ads
    
    def _parse_json_file(self, file_path: Path, source: str) -> List[Dict[str, Any]]:
        """
        Parse JSON file with ad data.
        
        Args:
            file_path: Path to JSON file
            source: Source identifier
            
        Returns:
            List of standardized ad data
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle different JSON structures
        if isinstance(data, list):
            ads = data
        elif isinstance(data, dict):
            # Try common key names
            ads = (
                data.get('ads') or 
                data.get('data') or 
                data.get('results') or 
                [data]
            )
        else:
            logger.error(f"Unexpected JSON structure in {file_path}")
            return []
        
        # Standardize ad data format
        standardized_ads = []
        for ad in ads:
            standardized_ad = self._standardize_ad_data(ad, source)
            if standardized_ad:
                standardized_ads.append(standardized_ad)
        
        return standardized_ads
    
    def _standardize_ad_data(self, ad_data: Dict[str, Any], source: str) -> Optional[Dict[str, Any]]:
        """
        Standardize ad data to common format.
        
        Args:
            ad_data: Raw ad data from extension
            source: Source identifier
            
        Returns:
            Standardized ad data or None if invalid
        """
        # Try to extract URL from various possible field names
        url = (
            ad_data.get('url') or
            ad_data.get('link') or
            ad_data.get('destination_url') or
            ad_data.get('landing_page') or
            ad_data.get('website') or
            ad_data.get('href')
        )
        
        if not url:
            logger.debug(f"No URL found in ad data: {ad_data}")
            return None
        
        # Extract other fields
        title = (
            ad_data.get('title') or
            ad_data.get('headline') or
            ad_data.get('ad_title') or
            ad_data.get('name') or
            ""
        )
        
        description = (
            ad_data.get('description') or
            ad_data.get('text') or
            ad_data.get('body') or
            ad_data.get('ad_text') or
            ""
        )
        
        # Create standardized ad data
        standardized = {
            "url": url,
            "title": title[:200] if title else "",
            "description": description[:500] if description else "",
            "source": source,
            "scraped_at": datetime.utcnow().isoformat(),
            "raw_data": ad_data  # Keep original data for reference
        }
        
        return standardized
    
    def _deduplicate_ads(self, ads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Remove duplicate ads based on URL.
        
        Args:
            ads: List of ad data
            
        Returns:
            List of unique ads
        """
        seen_urls = set()
        unique_ads = []
        
        for ad in ads:
            url = ad.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_ads.append(ad)
        
        return unique_ads
    
    @staticmethod
    def create_sample_data_files():
        """
        Create sample data files for testing.
        This can be used to create example files for the extensions.
        """
        sample_my_ad_finder = [
            {
                "url": "https://example-funnel1.com/webinar",
                "title": "Free Marketing Webinar",
                "description": "Learn the secrets of digital marketing",
                "date_found": "2024-01-15"
            },
            {
                "url": "https://example-funnel2.com/free-training",
                "title": "Master Facebook Ads",
                "description": "Step-by-step Facebook ads training",
                "date_found": "2024-01-16"
            }
        ]
        
        sample_turbo_ad_finder = [
            {
                "destination_url": "https://example-funnel3.com/masterclass",
                "headline": "Business Growth Masterclass",
                "ad_text": "Scale your business to 7 figures",
                "discovered": "2024-01-17"
            }
        ]
        
        # Create data directory
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        
        # Write sample files
        with open(data_dir / "my_ad_finder.json", 'w') as f:
            json.dump(sample_my_ad_finder, f, indent=2)
        
        with open(data_dir / "turbo_ad_finder.json", 'w') as f:
            json.dump(sample_turbo_ad_finder, f, indent=2)
        
        logger.info("Sample data files created in data/ directory")


if __name__ == "__main__":
    # Create sample data files when run directly
    ExtensionDataParser.create_sample_data_files()

