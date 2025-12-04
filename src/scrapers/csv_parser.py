"""
CSV data parser for training.csv
Reads ad URLs from training.csv file.
"""

import csv
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

from loguru import logger

from src.config import Config


class CSVDataParser:
    """Parse ad data from training.csv"""
    
    def __init__(self, config: Config):
        """
        Initialize CSV parser.
        
        Args:
            config: Application configuration
        """
        self.config = config
        self.csv_path = Path(config.sources.csv_data.data_path)
    
    def parse(self) -> List[Dict[str, Any]]:
        """
        Parse ads from CSV file.
        
        Returns:
            List of ad data dictionaries
        """
        if not self.csv_path.exists():
            logger.warning(f"CSV file not found: {self.csv_path}")
            return []
        
        ads = []
        
        try:
            with open(self.csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    # Skip rows with empty URLs
                    if not row.get('url') or not row['url'].strip():
                        continue
                    
                    ad_data = {
                        'url': row['url'].strip(),
                        'title': row.get('title', '').strip(),
                        'description': row.get('description', '').strip(),
                        'keyword': row.get('keyword', '').strip(),
                        'source': row.get('source', 'csv').strip(),
                        'scraped_at': row.get('scraped_at', datetime.utcnow().isoformat())
                    }
                    ads.append(ad_data)
            
            logger.success(f"✅ Loaded {len(ads)} ads from training.csv")
            
        except Exception as e:
            logger.error(f"Error parsing CSV file: {e}")
            return []
        
        return ads

