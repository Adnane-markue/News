import json
import logging
import os
import re
import time
from datetime import datetime
from hashlib import md5
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional
from urllib.parse import urljoin
import urllib.robotparser as robotparser
import dateparser
import requests


# -----------------------------
# Default Directories (auto-created)
# -----------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
ROBOTS_CACHE_DIR = os.path.join(DATA_DIR, "robots")

# -----------------------------
# Paths & directories
# -----------------------------
def ensure_dirs(*paths: str) -> None:
    """Create multiple directories if they don't exist."""
    for p in paths:
        os.makedirs(p, exist_ok=True)

ensure_dirs(DATA_DIR, LOGS_DIR, CACHE_DIR, ROBOTS_CACHE_DIR)

# -----------------------------
# Logging
# -----------------------------
def setup_logger(name: str, logs_dir: str = LOGS_DIR) -> logging.Logger:
    import logging
    from logging.handlers import RotatingFileHandler
    os.makedirs(logs_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')

    # 1️⃣ Rotating log (max 5 MB, 5 backups) for INFO+
    rotating_info = RotatingFileHandler(
        os.path.join(logs_dir, f'scraping.log'),
        maxBytes=5*1024*1024,
        backupCount=5,
        encoding='utf-8'
    )
    rotating_info.setLevel(logging.INFO)
    rotating_info.setFormatter(fmt)

    # 2️⃣ Daily INFO log
    daily_info = logging.FileHandler(
        os.path.join(logs_dir, f'scraping_{datetime.now().strftime("%Y%m%d")}.log'),
        encoding='utf-8'
    )
    daily_info.setLevel(logging.INFO)
    daily_info.setFormatter(fmt)

    # 3️⃣ Daily ERROR log (WARNING+ERROR)
    daily_err = logging.FileHandler(
        os.path.join(logs_dir, f'scraping_error_{datetime.now().strftime("%Y%m%d")}.log'),
        encoding='utf-8'
    )
    daily_err.setLevel(logging.WARNING)
    daily_err.setFormatter(fmt)

    # 4️⃣ Console output
    console = logging.StreamHandler()
    console.setFormatter(fmt)

    # Avoid duplicate handlers
    if not logger.handlers:
        logger.addHandler(rotating_info)
        logger.addHandler(daily_info)
        logger.addHandler(daily_err)
        logger.addHandler(console)

    # Silence noisy libs
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)

    return logger



# -----------------------------
# Robots.txt caching
# -----------------------------
class RobotsCache:
    """Cache robots.txt rules locally to avoid re-downloading too often."""

    def __init__(self, base_url: str, cache_dir: str = ROBOTS_CACHE_DIR, user_agent: str = "Mozilla/5.0"):
        self.base_url = base_url.rstrip('/')
        self.cache_dir = cache_dir
        self.user_agent = user_agent
        self.cache_path = os.path.join(
            cache_dir,
            md5((self.base_url + '/robots.txt').encode()).hexdigest() + '.robots'
        )
        ensure_dirs(cache_dir)

    def _load_from_disk(self) -> Optional[str]:
        """Load robots.txt from local cache if fresh (<24h)."""
        if not os.path.exists(self.cache_path):
            return None
        if time.time() - os.path.getmtime(self.cache_path) > 86400:
            return None
        try:
            with open(self.cache_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            return None

    def _save_to_disk(self, content: str) -> None:
        """Save robots.txt content to cache."""
        try:
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception:
            pass

    def is_allowed(self, url: str, logger: logging.Logger) -> bool:
        """Check if scraping is allowed by robots.txt."""

        # 🌐 Sites for which we bypass robots.txt checks
        IGNORED_ROBOTS = ["en.hespress.com", "alyaoum24.com"]

        # 🚨 Ignore robots.txt for sites in IGNORED_ROBOTS
        if any(site in self.base_url for site in IGNORED_ROBOTS):
            return True

        rp = robotparser.RobotFileParser()
        cached = self._load_from_disk()
        if cached:
            rp.parse(cached.splitlines())
            return rp.can_fetch(self.user_agent, url)
        try:
            rp.set_url(urljoin(self.base_url + '/', 'robots.txt'))
            rp.read()
            r = requests.get(urljoin(self.base_url + '/', 'robots.txt'), timeout=10)
            if r.ok:
                self._save_to_disk(r.text)
            return rp.can_fetch(self.user_agent, url)
        except Exception as e:
            logger.warning(f"Robots.txt check failed ({e}); proceeding cautiously.")
            return True




# -----------------------------
# Cache & hashing
# -----------------------------
def url_cache_path(cache_dir: str, url: str) -> str:
    return os.path.join(cache_dir, md5(url.encode()).hexdigest() + '.json')


def content_hash(text: str) -> str:
    return md5((text or '').encode()).hexdigest()


def load_light_cache(cache_dir: str, url: str) -> Optional[Dict[str, Any]]:
    path = url_cache_path(cache_dir, url)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def save_light_cache(cache_dir: str, url: str, payload: Dict[str, Any]) -> None:
    ensure_dirs(cache_dir)
    path = url_cache_path(cache_dir, url)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception:
        pass


# -----------------------------
# Dates & parsing helpers
# -----------------------------
import dateparser

def parse_date_maybe(s: Optional[str], languages: Optional[list] = None) -> Optional[str]:
    """Parse a date string and return ISO 8601 format."""
    if not s:
        return None
    # Try parsing with Arabic first, then fallback to French/English
    dt = dateparser.parse(s, languages=languages or ['ar', 'fr', 'en'])
    if not dt:
        return None
    return dt.isoformat()



# -----------------------------
# JSON saving
# -----------------------------
def save_json(path: str, obj: Dict[str, Any]) -> None:
    ensure_dirs(os.path.dirname(path))
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# -----------------------------
# Text cleanup
# -----------------------------
def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or '').strip()
