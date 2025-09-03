import argparse
import json
import time
import os
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Set, Union
from urllib.parse import urljoin, urlparse
from src.tools.screenshots import take_screenshot 
from .api_client import NewsAPIClient  
import requests
import yaml
from bs4 import BeautifulSoup, Tag
from playwright.sync_api import sync_playwright

from .utils import (
    ensure_dirs,
    setup_logger,
    RobotsCache,
    content_hash,
    load_light_cache,
    save_light_cache,
    normalize_ws,
    save_json,
    parse_date_maybe,
)

Selector = Union[str, Dict[str, str]]  # either "a.css" or {css: "a.css", attr: "href"}


class GenericNewsScraper:
    def __init__(self, config_path: str, data_dir: str = 'data', logs_dir: str = 'logs', enable_api: bool = True):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.cfg = yaml.safe_load(f)

        self.site_key: str = self.cfg.get('site_key') or os.path.splitext(os.path.basename(config_path))[0]
        self.site_name: str = self.cfg.get('name', self.site_key)
        self.base_url: str = self.cfg['base_url'].rstrip('/')
        self.headers: Dict[str, str] = self.cfg.get('headers', {
            'User-Agent': f'NewsScraperBot/1.0 (+https://example.com/{self.site_key})'
        })
        self.language: Optional[str] = self.cfg.get('language')
        self.timeout: int = int(self.cfg.get('timeout', 15))
        self.max_retries: int = int(self.cfg.get('max_retries', 3))
        self.delay_seconds: float = float(self.cfg.get('delay_seconds', 1.5))
        self.selectors: Dict[str, List[Selector]] = self.cfg.get('selectors', {})
        self.filters: Dict[str, List[str]] = self.cfg.get('filters', {})
        self.pagination_cfg: Dict[str, str] = self.cfg.get('pagination', {
            'type': 'suffix', 'first_page': '', 'next_page': 'page/{page}/'
        })
        self.categories_map: Dict[str, str] = self.cfg.get('categories', {'home': '/'})

        # Dirs
        self.data_dir = data_dir
        self.raw_dir = os.path.join(data_dir, 'raw')
        self.processed_dir = os.path.join(data_dir, 'processed')
        self.cache_dir = os.path.join(data_dir, 'cache')
        self.logs_dir = logs_dir
        self.screenshots_dir = os.path.join(data_dir, 'screenshots')
        ensure_dirs(self.raw_dir, self.processed_dir, self.cache_dir, self.logs_dir, self.screenshots_dir)
          

        self.logger = setup_logger(self.site_key, self.logs_dir)
        self.robots = RobotsCache(self.base_url, self.cache_dir, self.headers.get('User-Agent', 'NewsScraperBot'))
        self.session = requests.Session()
        self.session.headers.update(self.headers)

        # Playwright toggle (default True for JS-heavy sites)
        self.use_playwright: bool = bool(self.cfg.get('js_render', False))

        # Precompute base netloc for same-domain checks
        self._base_netloc = urlparse(self.base_url).netloc
        # API Integration
        self.enable_api = enable_api
        self.api_client = NewsAPIClient() if enable_api else None

    # -----------------------------
    # HTTP & JS fetch
    # -----------------------------
    def request_with_retries(self, url: str) -> Optional[requests.Response]:
        headers = self.headers.copy()
        for attempt in range(1, self.max_retries + 1):
            try:
                r = self.session.get(url, timeout=self.timeout, headers=headers)
                r.raise_for_status()
                low = r.text.lower()
                if any(x in low for x in ['captcha', 'cloudflare', 'access denied']):
                    self.logger.warning(f"Potential blocking text detected at {url}")
                    return None
                return r
            except Exception as e:
                self.logger.warning(f"Attempt {attempt}/{self.max_retries} failed for {url}: {e}")
                if attempt < self.max_retries:
                    time.sleep(self.delay_seconds * attempt)
        return None

    def fetch_with_playwright(self, url: str) -> Optional[str]:
        self.logger.info(f"Using Playwright for JS-protected site: {url}")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
                content = page.content()
                browser.close()
                return content
        except Exception as e:
            self.logger.warning(f"Playwright fetch failed for {url}: {e}")
            return None

    def soup(self, html_or_resp) -> BeautifulSoup:
        text = html_or_resp.text if hasattr(html_or_resp, 'text') else html_or_resp
        return BeautifulSoup(text, 'html.parser')

    def can_fetch(self, full_url: str) -> bool:
        try:
            return self.robots.is_allowed(full_url, self.logger)
        except Exception:
            return True

    # -----------------------------
    # Selector helpers
    # -----------------------------
    def _iter_selectors(self, key: str) -> List[Selector]:
        vals = self.selectors.get(key, [])
        return vals if isinstance(vals, list) else []

    def select_first(self, root: BeautifulSoup | Tag, key: str) -> Optional[str]:
        for sel in self._iter_selectors(key):
            if isinstance(sel, str):
                el = root.select_one(sel)
                if el:
                    if el.has_attr('content'):
                        return el.get('content')
                    return el.get_text(strip=True)
            elif isinstance(sel, dict):
                css = sel.get('css')
                attr = sel.get('attr')
                if not css:
                    continue
                el = root.select_one(css)
                if el:
                    return (el.get(attr) if attr else None) or el.get('content') or el.get_text(strip=True)
        return None

    def select_first_tag(self, root: BeautifulSoup | Tag, key: str) -> Optional[Tag]:
        for sel in self._iter_selectors(key):
            css = sel if isinstance(sel, str) else sel.get('css')
            if not css:
                continue
            el = root.select_one(css)
            if el:
                return el
        return None

    # -----------------------------
    # JSON-LD extraction
    # -----------------------------
    def extract_json_ld(self, soup: BeautifulSoup) -> Dict:
        data = {}
        for script in soup.select("script[type='application/ld+json']"):
            try:
                js = json.loads(script.string, strict=False)
                if isinstance(js, dict):
                    data.update(js)
                elif isinstance(js, list):
                    for item in js:
                        if isinstance(item, dict):
                            data.update(item)
            except Exception:
                continue
        return data

    # -----------------------------
    # URL filtering
    # -----------------------------
    def _same_domain(self, url: str) -> bool:
        try:
            return urlparse(url).netloc.endswith(self._base_netloc)
        except Exception:
            return False

    def _is_article_url(self, url: str) -> bool:
        if not url or not url.startswith("http"):
            return False
        if not self._same_domain(url):
            return False

        bad_subs = set(self.filters.get('exclude_substrings', []))
        for b in bad_subs:
            if b and b in url:
                return False

        deny_regexes = self.filters.get('deny_regex', [])
        for rx in deny_regexes:
            try:
                if re.search(rx, url):
                    return False
            except re.error:
                pass

        allow_regexes = self.filters.get('allow_regex', [])
        if allow_regexes:
            for rx in allow_regexes:
                try:
                    if re.search(rx, url):
                        return True
                except re.error:
                    pass
            return False

        return True

    # -----------------------------
    # Article lists
    # -----------------------------
    def extract_links_from_page(self, soup: BeautifulSoup) -> List[str]:
        links: Set[str] = set()
        for sel in self._iter_selectors('article_links'):
            css = sel if isinstance(sel, str) else sel.get('css')
            if not css:
                continue
            for a in soup.select(css):
                href = a.get('href')
                if not href:
                    continue
                full = urljoin(self.base_url + '/', href)
                if self._is_article_url(full):
                    links.add(full)

        if not links:
            for a in soup.select('a[href]'):
                href = a.get('href')
                if not href:
                    continue
                full = urljoin(self.base_url + '/', href)
                if self._is_article_url(full):
                    links.add(full)
        self.logger.debug(f"Found {len(links)} articles on this page")
        return list(links)

    def page_url(self, category_path: str, page: int) -> str:
        cat = urljoin(self.base_url + '/', category_path.lstrip('/'))
        p = self.pagination_cfg
        suffix = p.get('first_page', '') if page <= 1 else p.get('next_page', 'page/{page}/').format(page=page)
        return urljoin(cat.rstrip('/') + '/', suffix)

    def scrape_category(self, category_path: str, max_articles: int, max_pages: int) -> List[str]:
        urls: List[str] = []
        page = 1
        while len(urls) < max_articles and page <= max_pages:
            url = self.page_url(category_path, page)
            self.logger.info(f"Scrape list page {page}: {url}")
            if not self.can_fetch(url):
                self.logger.warning(f"Disallowed by robots.txt: {url}")
                break

            html = self.fetch_with_playwright(url) if self.use_playwright else None
            if not html:
                resp = self.request_with_retries(url)
                if not resp:
                    break
                soup = self.soup(resp)
            else:
                soup = self.soup(html)

            found = self.extract_links_from_page(soup)
            for link in found:
                if len(urls) >= max_articles:
                    break
                urls.append(link)

            page += 1
            time.sleep(self.delay_seconds)
        return urls

    # -----------------------------
    # Article pages
    # -----------------------------
    def extract_content(self, soup: BeautifulSoup) -> str:
        container = None
        for sel in self._iter_selectors('content'):
            container = soup.select_one(sel)
            if container:
                break
        if not container and self.use_playwright:
            self.logger.info("Trying Playwright-rendered content fallback")
            container = soup.select_one('article, .article-content, .entry-content, .post-content, .content')
        if not container:
            return ''

        for sel in self._iter_selectors('content_remove'):
            css = sel if isinstance(sel, str) else sel.get('css')
            if not css:
                continue
            for bad in container.select(css):
                bad.decompose()

        texts: List[str] = []
        paragraph_selector = ', '.join(self.cfg.get('content_text_elems', ['p', 'li', 'div']))
        for node in container.select(paragraph_selector):
            if isinstance(node, Tag):
                t = node.get_text(separator=' ', strip=True)
                t = normalize_ws(t)
                if t:
                    texts.append(t)

        out: List[str] = []
        for t in texts:
            if not out or content_hash(t) != content_hash(out[-1]):
                out.append(t)
        return '\n'.join(out)

    def extract_image(self, soup: BeautifulSoup) -> Optional[str]:
        img = self.select_first(soup, 'image')
        if img and img.startswith('http'):
            return img
        og = soup.select_one('meta[property="og:image"], meta[name="og:image"]')
        if og and og.get('content'):
            return og.get('content')
        tag = soup.select_one('img[src]')
        if tag and tag.get('src'):
            return urljoin(self.base_url + '/', tag.get('src'))
        return None

    def scrape_article(self, url: str) -> Optional[Dict]:
        if not self.can_fetch(url):
            self.logger.warning(f"Disallowed by robots.txt (article): {url}")
            return None

        html = self.fetch_with_playwright(url) if self.use_playwright else None
        if not html:
            resp = self.request_with_retries(url)
            if not resp:
                return None
            soup = self.soup(resp)
        else:
            soup = self.soup(html)

        title = self.select_first(soup, 'title') or (
            soup.find('title').get_text(strip=True) if soup.find('title') else None
        )
        content = self.extract_content(soup)
        if not title and not content:
            self.logger.warning(f"Empty article: {url}")
            return None

        # JSON-LD fallback
        json_ld = self.extract_json_ld(soup)
        author = self.select_first(soup, 'author')
        date_raw = self.select_first(soup, 'date')
        category = self.select_first(soup, 'category') or "uncategorized"

        if not author:
            author = json_ld.get('author', {}).get('name') if isinstance(json_ld.get('author'), dict) else json_ld.get('author')
        if not date_raw:
            date_raw = json_ld.get('datePublished')
        if category == "uncategorized":
            category = json_ld.get('articleSection')

        # postprocess regex from YAML
        if (not author or not date_raw) and content:
            first_line = content.split('\n')[0]
            post = self.cfg.get('postprocess', {})

            if not author and post.get('author', {}).get('regex'):
                m = re.search(post['author']['regex'], first_line)
                if m:
                    author = m.group(1).strip()

            if not date_raw and post.get('date', {}).get('regex'):
                m = re.search(post['date']['regex'], first_line)
                if m:
                    date_raw = m.group(1).strip()


        image_url = self.extract_image(soup)
        chash = content_hash(content)

        prior = load_light_cache(self.cache_dir, url)
        if prior and prior.get('content_hash') == chash:
            self.logger.info(f"Unchanged content; skipping: {url}")
            return None

        # Take screenshot
        screenshot_path = None
        if self.cfg.get('take_screenshots', False):  # Configurable
            try:
                filename = f"{content_hash(url)}.png"
                screenshot_path = take_screenshot(
                    url, 
                    os.path.join(self.screenshots_dir, self.site_key),
                    filename
                )
            except Exception as e:
                self.logger.error(f"Screenshot failed for {url}: {e}")

        doc = {
            'id': content_hash(url),
            'site_key': self.site_key,
            'site_name': self.site_name,
            'language': self.language,
            'url': url,
            'title': title,
            'content': content,
            'author': author,
            'date_raw': date_raw,
            'category': category,
            'image_url': image_url,
            'scraped_at': datetime.utcnow().isoformat() + 'Z',
            'screenshot_path': screenshot_path,
            'screenshot_taken_at': datetime.utcnow().isoformat() + 'Z' if screenshot_path else None
        }

        # # Save to API if enabled
        # if self.api_client:
        #     try:
        #         api_success = self.api_client.send_article(doc)
        #         if not api_success:
        #             self.logger.warning(f"API save failed for {url}, falling back to local only")
        #     except Exception as e:
        #         self.logger.error(f"API communication error: {str(e)}")

        # Always keep local backup
        save_light_cache(self.cache_dir, url, {
            'url': url,
            'title': title,
            'date': date_raw,
            'category': category,
            'content_hash': chash,
            'scraped_at': doc['scraped_at']
        })

        ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        raw_name = f"{self.site_key}_{ts}_{doc['id'][:8]}.json"
        save_json(os.path.join(self.raw_dir, raw_name), doc)

        category_safe = re.sub(r'\W+', '_', (category or 'uncategorized')).lower()
        proc_dir = os.path.join(self.processed_dir, self.site_key, 'classified', category_safe)
        ensure_dirs(proc_dir)
        proc_name = f"{datetime.utcnow().strftime('%Y%m%d')}_{content_hash((title or '') + (category or ''))[:10]}.json"
        save_json(os.path.join(proc_dir, proc_name), doc)

        self.logger.info(f"Saved: {title} -> {proc_name}")
        return doc


    # -----------------------------
    # Orchestration
    # -----------------------------
    def run(self, categories: List[str], limit: int, max_pages: int) -> List[Dict]:
        self.logger.info(f"Starting scraper for {self.site_name} ({self.site_key}) ...")
        collected: List[Dict] = []
        seen: Set[str] = set()

        if not categories:
            categories = list(self.categories_map.keys())
        per = max(1, limit // max(1, len(categories)))

        for cat_key in categories:
            if len(collected) >= limit:
                break
            path = self.categories_map.get(cat_key, cat_key)
            urls = self.scrape_category(path, max_articles=per, max_pages=max_pages)
            for u in urls:
                if len(collected) >= limit:
                    break
                if u in seen:
                    continue
                seen.add(u)
                art = self.scrape_article(u)
                if art:
                    collected.append(art)
                time.sleep(self.delay_seconds)

        if len(collected) < limit and self.categories_map.get('home'):
            remaining = limit - len(collected)
            self.logger.info(f"Topping up {remaining} from homepage ...")
            urls = self.scrape_category(self.categories_map['home'], max_articles=remaining, max_pages=1)
            for u in urls:
                if len(collected) >= limit:
                    break
                if u in seen:
                    continue
                seen.add(u)
                art = self.scrape_article(u)
                if art:
                    collected.append(art)
                time.sleep(self.delay_seconds)
                
        # Send batch to API at the end
        if self.api_client and collected:
            self.logger.info(f"Sending {len(collected)} articles to API...")
            
            start_time = time.time()  # Start timer
            
            batch_result = self.api_client.send_batch(collected, batch_size=50)
            
            end_time = time.time()  # End timer
            processing_time = end_time - start_time
            
            # Calculate metrics
            total_processed = batch_result["inserted"] + batch_result["duplicates"] + batch_result["failed"]
            success_rate = (batch_result["inserted"] + batch_result["duplicates"]) / total_processed * 100 if total_processed > 0 else 0
            articles_per_second = total_processed / processing_time if processing_time > 0 else 0
            
            self.logger.info(
                f"Batch API complete: {batch_result['inserted']} inserted, "
                f"{batch_result['duplicates']} duplicates, "
                f"{batch_result['failed']} failed, "
                f"{success_rate:.1f}% success rate, "
                f"in {processing_time:.2f} seconds "
                f"({articles_per_second:.1f} articles/sec)"
            )

        self.logger.info(f"Done. Total articles: {len(collected)}")
        return collected


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Generic YAML-driven news scraper')
    p.add_argument('--site', type=str, help='Site key (e.g., hespress_fr)')
    p.add_argument('--config', type=str, help='YAML config path')
    p.add_argument('--categories', type=str, nargs='*', default=None)
    p.add_argument('--limit', type=int, default=20)
    p.add_argument('--max_pages', type=int, default=5)
    p.add_argument('--data_dir', type=str, default='data')
    p.add_argument('--logs_dir', type=str, default='logs')
    p.add_argument('--disable-api', action='store_true', help='Disable API saving')
    return p
