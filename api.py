import requests
from typing import List, Dict, Optional

class APIClient:
    GLOBAL_CONFIG_URL = "https://api.mmoui.com/v3/globalconfig.json"
    GAME_ID = "ESO"
    
    def __init__(self):
        self.headers = {
            'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            'Accept-Encoding': 'gzip, deflate'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        self.game_config_url = None
        self.file_list_url = None
        self.file_details_url = None
        self.list_files_url = None
        self.category_list_url = None
        self.categories: List[Dict] = []
        self.addons: List[Dict] = []
        
    def _fetch_json(self, url: str) -> dict | list:
        # 10s timeout to prevent hanging forever
        response = self.session.get(url, timeout=15)
        response.raise_for_status()
        return response.json()
            
    def initialize(self):
        # 1. Fetch Global Config
        global_config = self._fetch_json(self.GLOBAL_CONFIG_URL)
        for game in global_config.get("GAMES", []):
            if game.get("GameID") == self.GAME_ID:
                self.game_config_url = game.get("GameConfig")
                break
        
        if not self.game_config_url:
            raise Exception("ESO Game Configuration URL not found.")
            
        # 2. Fetch Game Config
        game_config = self._fetch_json(self.game_config_url)
        feeds = game_config.get("APIFeeds", {})
        self.file_list_url = feeds.get("FileList")
        self.file_details_url = feeds.get("FileDetails")
        self.list_files_url = feeds.get("ListFiles")
        self.category_list_url = feeds.get("CategoryList")
        
    def fetch_categories(self) -> List[Dict]:
        if not self.category_list_url:
            self.initialize()
        self.categories = self._fetch_json(self.category_list_url)
        return self.categories
        
    def fetch_addons(self) -> List[Dict]:
        if not self.file_list_url:
            self.initialize()
        self.addons = self._fetch_json(self.file_list_url)
        return self.addons
        
    def fetch_addon_details(self, addon_id: str) -> Dict:
        if not self.file_details_url:
            self.initialize()
        url = f"{self.file_details_url}{addon_id}.json"
        data = self._fetch_json(url)
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        return {}
