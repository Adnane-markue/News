from playwright.sync_api import sync_playwright
import os
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse
import time

# Unified domain selectors - all domain knowledge in one place
DOMAIN_SELECTORS = {
    # Original domains from smart_article_detection
    "icirabat.com": ["article", ".post-content", ".news-content", ".story-content"],
    "icinador.com": ["article", ".post-content", ".story-content"],
    "icimeknes.com": ["article", ".entry-content", ".news-body"],
    "icimarrakech.com": ["article", ".post-content", ".news-body"],
    "iciguercif.com": ["article", ".story-content", ".post-content"],
    "icifes.com": ["article", ".post-content", ".news-body"],
    "icidakhla.com": ["article", ".story-content", ".article-body"],
    "icicasa.com": ["article", ".entry-content", ".story-content"],
    "iciagadir.com": ["article", ".news-content", ".post-content"],
    "ichrakanews.com": ["article", ".post-content", ".article-body"],
    "i3lamtv.com": ["article", ".content-wrapper", ".article-body"],
    "i3lam24.com": ["article", ".post-content", ".news-body"],
    "howiyapress.com": ["article", ".post-content", ".story-content"],
    "hounasahara.net": ["article", ".entry-content", ".news-body"],
    "horiapress.com": ["article", ".post-content", ".story-content"],
    "hona24.net": ["article", ".post-content", ".article-body"],
    "homepress.ma": ["article", ".entry-content", ".news-body"],
    "hnews.ma": ["article", ".news-content", ".story-content"],
    "hibazoom.com": ["article", ".post-content", ".article-body"],
    "hibasport.com": ["article", ".story-content", ".post-content"],
    
    # New domains with specific issues
    "alassima24.ma": [".article-content", ".post-content", ".entry-content", "article", ".content", ".details"],
    "alhoriyanews.com": [".news-details", ".article-body", ".content", "article", ".post", ".single-content"],
    "almaghribtoday.net": [".article-content", ".post-content", ".entry-content", "article", ".content"],
    "achamalpress.com": [".article-content", ".post-content", ".news-body", "article", ".content", ".single-post"],
    "achtari24.com": [".news-details", ".article-body", ".content", "article", ".post", ".td-post-content"],
    "al_montakhab": [".article-content", ".post-content", ".entry-content", "article", ".content"],
    "ecopress.ma": [".article-content", ".post-content", ".entry-content", "article", ".content"],
    "dakhlapress.net": [".article-content", ".post-content", ".entry-content", "article", ".content", ".single-content"],
    "aujourdhui.ma": [".article-content", ".post-content", ".entry-content", "article", ".content", ".td-post-content"],
    "alnoortv.ma": [".td-post-content", ".td-container", ".td-main-content", "article", ".post"],
    "actu-maroc.com": [".article-content", ".post-content", ".entry-content", "article", ".content"],
    
    # Domains from CONTENT_SELECTORS
    "ar.hibapress.com": ["article", ".story-content", ".news-body"],
    "fr.hibapress.com": ["article", ".story-content", ".news-body"],
    "www.fr.heuredujournal.com": ["article", ".article-container", ".content-main"],
    "ar.heuredujournal.com": ["article", ".article-container", ".content-main"],
    "www.icitetouan.com": ["article", ".post-content", ".entry-content", ".news-body"],
    "icitetouan.com": ["article", ".post-content", ".entry-content", ".news-body"],
    
    # New addition: Zone24
    "zone24.ma": [".post-content", ".post-body", "article", ".post-content", ".entry-content", ".news-body"],
    "zaiocity.net": ["content-inner", "jeg_inner_content",  "jeg_main_content", "jeg_main_content col-md-8", ".row"],
    "zahramagazine.net": [".article.clearfix", ".entry", ".entry, .article.clearfix ", ".content-area", ".article.clearfix"]

    # Add more domains as you discover them
}

# Domain-specific timing optimization
DOMAIN_TIMING = {
    'mediamarketing.ma': 1000,    # 1 second
    'media90.ma': 1000,           # 1 second
    'medialive.ma': 1500,         # 1.5 seconds
    'banassa.info': 1000,         # 1 second
    'alyaoum24.com': 1500,        # 1.5 seconds
    'aujourdhui.ma': 2500,        # 2.5 seconds (slow site)
    'hespress.com': 2500,         # 2.5 seconds (slow site)
    'au-maroc.info': 2000,        # 2 seconds
    # Add more domains as you discover their load times
}

def get_domain_wait_time(url):
    domain = urlparse(url).netloc.lower()
    return DOMAIN_TIMING.get(domain, 2000)  # Default 2 seconds

def take_screenshot(url: str, output_dir: str, filename: str, format: str = 'png') -> Optional[str]:
    """
    Take screenshot of a webpage and save to file
    Returns: path to saved screenshot or None if failed
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)  # Reduced from 5000 to 2000

            # --- Enhanced popup handling ---
            try:
                # More comprehensive popup closing
                page.evaluate("""
                    // Hide all common popup elements
                    const popupSelectors = [
                        '.popup', '.modal', '.cookie-banner', '.gdpr', '.consent',
                        '.newsletter-popup', '.ml-popup', '#newsletter-popup',
                        '.subscribe-popup', '.popup-newsletter'
                    ];
                    
                    popupSelectors.forEach(selector => {
                        document.querySelectorAll(selector).forEach(el => {
                            el.style.display = 'none';
                            el.remove();
                        });
                    });

                    // Click all close buttons
                    document.querySelectorAll('.close, .popup-close, [aria-label*="Close"], [aria-label*="Fermer"], [onclick*="close"]')
                        .forEach(btn => {
                            try { btn.click(); } catch(e) {}
                        });

                    // Remove overlay backgrounds
                    document.querySelectorAll('.overlay, .modal-backdrop, .popup-overlay')
                        .forEach(el => {
                            el.style.display = 'none';
                            el.remove();
                        });
                """)
                
                # Additional click attempts for specific sites
                close_buttons = page.query_selector_all("button:has-text('×'), button:has-text('Close'), button:has-text('Fermer'), [aria-label*='Close'], [aria-label*='Fermer']")
                for button in close_buttons:
                    try:
                        button.click()
                        page.wait_for_timeout(500)
                    except:
                        pass
                    
            except Exception as e:
                print(f"Popup handling skipped: {e}")

            # --- Enhanced background colors ---
            try:
                page.evaluate("""
                    // Ensure proper background for screenshots
                    document.body.style.background = 'white';
                    document.body.style.backgroundColor = 'white';
                    
                    // Also fix potential parent elements
                    document.querySelectorAll('div, section, article').forEach(el => {
                        if (window.getComputedStyle(el).backgroundColor === 'transparent' || 
                            window.getComputedStyle(el).backgroundColor === 'rgba(0, 0, 0, 0)') {
                            el.style.backgroundColor = 'white';
                        }
                    });
                """)
            except:
                pass

            # Create screenshots directory
            os.makedirs(output_dir, exist_ok=True)

            # Generate filename with correct extension
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"screenshot_{timestamp}.{format}"
            elif not filename.endswith(f'.{format}'):
                # Ensure filename has the correct extension
                filename = f"{os.path.splitext(filename)[0]}.{format}"

            screenshot_path = os.path.join(output_dir, filename)
            
            # Configure screenshot options based on format
            screenshot_options = {
                'path': screenshot_path,
                'full_page': True
            }
            
            # Only specify type if not default PNG
            if format != 'png':
                screenshot_options['type'] = format
                
            page.screenshot(**screenshot_options)

            browser.close()
            return screenshot_path

    except Exception as e:
        print(f"Screenshot failed for {url}: {e}")
        return None

def find_content_aggressively(page):
    """More aggressive content detection for difficult sites"""
    try:
        # Strategy 1: Look for the largest text block
        text_elements = page.query_selector_all('div, section, article, p')
        best_element = None
        max_text = 0
        
        for element in text_elements:
            try:
                box = element.bounding_box()
                if not box or box['width'] < 300 or box['height'] < 200:
                    continue
                
                text_length = element.evaluate('el => el.textContent.length')
                if text_length > max_text and text_length > 500:
                    max_text = text_length
                    best_element = element
            except:
                continue
        
        if best_element:
            print(f"✓ Found largest text block: {max_text} chars")
            return best_element
        
        # Strategy 2: Look for elements with many <p> tags (article-like)
        all_elements = page.query_selector_all('*')
        best_paragraph_element = None
        max_paragraphs = 0
        
        for element in all_elements:
            try:
                paragraphs = element.query_selector_all('p')
                if len(paragraphs) > 3:  # Article-like content
                    box = element.bounding_box()
                    if box and box['width'] > 400 and box['height'] > 300:
                        if len(paragraphs) > max_paragraphs:
                            max_paragraphs = len(paragraphs)
                            best_paragraph_element = element
            except:
                continue
        
        if best_paragraph_element:
            print(f"✓ Found element with {max_paragraphs} paragraphs")
            return best_paragraph_element
        
        print("⚠ No content found with aggressive detection")
        return None
        
    except Exception as e:
        print(f"Aggressive detection failed: {e}")
        return None

def enhanced_content_detection(page, url):
    """More aggressive content detection for difficult sites that show only images"""
    domain = urlparse(url).netloc.lower() if url else ""
    
    # Sites that tend to show only images
    image_only_sites = ["achtari24.com", "al_montakhab", "ecopress.ma"]
    
    if domain in image_only_sites:
        print(f"⚠ Using enhanced detection for {domain}")
        
        # Try to find the main content by looking for text-rich elements
        candidates = page.query_selector_all('div, section, article, main')
        
        best_candidate = None
        max_text_length = 0
        
        for candidate in candidates:
            try:
                box = candidate.bounding_box()
                if not box or box['width'] < 300 or box['height'] < 200:
                    continue
                
                text = candidate.evaluate("el => el.textContent.trim()")
                text_length = len(text)
                
                # Look for elements with substantial text content
                if text_length > 500 and text_length > max_text_length:
                    max_text_length = text_length
                    best_candidate = candidate
                    
            except:
                continue
        
        return best_candidate
    
    return None

def fast_article_detection(page, url):
    """Quick content detection for most common cases"""
    domain = urlparse(url).netloc.lower() if url else ""
    
    # Try domain-specific selectors first
    if domain in DOMAIN_SELECTORS:
        for selector in DOMAIN_SELECTORS[domain]:
            try:
                element = page.query_selector(selector)
                if element:
                    box = element.bounding_box()
                    if box and box['width'] > 300 and box['height'] > 200:
                        print(f"✓ Fast detection found: {selector} for {domain}")
                        return element
            except:
                continue
    
    # Try the most effective generic selectors
    fast_selectors = ['article', '[class*="content"]', '[class*="article"]']
    
    for selector in fast_selectors:
        try:
            element = page.query_selector(selector)
            if element:
                box = element.bounding_box()
                if box and box['width'] > 300 and box['height'] > 200:
                    return element
        except:
            continue
    
    return None

def smart_article_detection(page, url=None):
    """
    Smart detection optimized for Moroccan/Arabic news sites.
    Tries to isolate:
    - Title
    - Main image
    - Article text
    """
    try:
        # Use the global DOMAIN_SELECTORS
        domain = None
        selectors = []

        if url:
            domain = urlparse(url).netloc.lower()
            selectors = DOMAIN_SELECTORS.get(domain, [])

        # Enhanced Moroccan site patterns
        MOROCCAN_SITE_PATTERNS = [
            # Common Moroccan news site selectors
            ".article-content", ".news-content", ".details-content",
            ".post-content", ".story-content", ".news-body",
            ".article-body", ".entry-content", ".content-article",
            ".single-content", ".main-content", ".td-post-content",
            # Arabic-specific patterns
            "[class*='تفاصيل']", "[class*='محتوى']", "[class*='خبر']",
            "[id*='content']", "[id*='article']", "[id*='news']"
        ]

        # Generic fallback selectors
        generic_selectors = [
            "article", ".entry-content", ".post-content",
            ".story-content", ".news-content", ".article-body",
            "main", ".content"
        ]

        all_selectors = selectors + MOROCCAN_SITE_PATTERNS + generic_selectors

        best_candidate = None
        best_score = 0

        # Scan all selectors
        for selector in all_selectors:
            try:
                elements = page.query_selector_all(selector)
                for el in elements:
                    box = el.bounding_box()
                    if not box or box['width'] < 300 or box['height'] < 200:
                        continue

                    text_len = el.evaluate("el => el.textContent.length")
                    word_count = el.evaluate("el => el.textContent.split(/\s+/).length")
                    score = text_len + (2500 if selector in ['article', 'main'] else 0)

                    class_name = (el.get_attribute("class") or "").lower()
                    element_id = (el.get_attribute("id") or "").lower()

                    # Boost for content-related classes/IDs
                    if any(k in class_name for k in ["content", "post", "article", "story", "entry"]):
                        score += 1500
                    if any(k in element_id for k in ["content", "main", "article", "post"]):
                        score += 1500

                    # Penalize navigation/menu/sidebar
                    if any(k in class_name for k in ["nav", "menu", "sidebar", "widget"]):
                        score -= 3000

                    if score > best_score and word_count > 50 and text_len > 300:
                        best_score = score
                        best_candidate = el
            except Exception:
                continue

        if best_candidate:
            print(f"✓ Smart detection found article (score: {best_score}) for {domain or 'unknown domain'}")
            return best_candidate

        # --- Aggressive fallback ---
        print("⚠ No ideal article found, using aggressive fallback")
        return find_content_aggressively(page)

    except Exception as e:
        print(f"⚠ Smart detection failed: {e}")
        return None

def take_complete_article_screenshot(page, screenshot_path, format: str = 'png'):
    """Smarter fallback method to capture article content"""
    try:
        # First try to identify and isolate the main content area
        page.evaluate("""
            // Hide common non-content elements more aggressively
            const selectorsToHide = [
                'header', 'footer', 'nav', 'aside', '.sidebar',
                '.navbar', '.menu', '.advertisement', '.ads',
                '.social-share', '.comments', '.related-posts',
                '.popup', '.modal', '.newsletter', '.cookie-banner',
                '.header', '.footer', '.navigation', '.menu-item',
                '.widget', '.banner', '.ad', '.sponsor',
                '.share-buttons', '.comment-section', '.recommendations'
            ];
            
            // Also hide elements that are likely not content
            const allElements = document.querySelectorAll('*');
            allElements.forEach(el => {
                const style = window.getComputedStyle(el);
                const text = el.textContent || '';
                
                // Hide elements that are probably not main content
                if (el.offsetHeight < 50 && el.offsetWidth < 50) return; // Too small
                if (style.position === 'fixed') el.style.display = 'none'; // Fixed position elements
                if (text.length < 20 && el.children.length === 0) return; // Very little text
                
                // Check if element looks like navigation/menu
                const classList = Array.from(el.classList);
                const id = el.id.toLowerCase();
                const isNavLike = classList.some(cls => 
                    ['nav', 'menu', 'bar', 'btn', 'button'].some(word => cls.toLowerCase().includes(word))
                ) || id.includes('nav') || id.includes('menu');
                
                if (isNavLike) {
                    el.style.display = 'none';
                }
            });
            
            selectorsToHide.forEach(selector => {
                document.querySelectorAll(selector).forEach(el => {
                    el.style.display = 'none';
                });
            });
        """)
        
        page.wait_for_timeout(1500)
        
        # Try to find the main content area after hiding non-content
        main_content = page.query_selector('body > *:not(script):not(style)')
        if main_content:
            try:
                box = main_content.bounding_box()
                if box and box['height'] > 500:
                    # Configure screenshot options based on format
                    screenshot_options = {'path': screenshot_path}
                    if format != 'png':
                        screenshot_options['type'] = format
                    main_content.screenshot(**screenshot_options)
                    print("✓ Isolated main content screenshot")
                    return
            except:
                pass
        
        # Final fallback: full page but try to scroll to content
        page.evaluate("window.scrollTo(0, 200)")  # Scroll past header
        page.wait_for_timeout(500)
        
        # Configure screenshot options based on format
        screenshot_options = {
            'path': screenshot_path,
            'full_page': True
        }
        if format != 'png':
            screenshot_options['type'] = format
            
        page.screenshot(**screenshot_options)
        print("✓ Full page screenshot (cleaned)")
        
    except Exception as e:
        print(f"⚠ Fallback method failed: {e}")
        
        # Configure screenshot options based on format for fallback
        screenshot_options = {
            'path': screenshot_path,
            'full_page': True
        }
        if format != 'png':
            screenshot_options['type'] = format
            
        page.screenshot(**screenshot_options)
        print("✓ Regular full page screenshot saved")
        
def take_content_screenshot(url: str, output_dir: str, filename: str, selector: Optional[str] = None, format: str = 'png') -> Optional[str]:
    """
    Take screenshot of the main article content only.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
            page = browser.new_page()
            page.set_viewport_size({"width": 1200, "height": 800})
            
            # --- START TIMING ---
            start_time = time.time()
            
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            
            # --- ADAPTIVE WAITING - NEW CODE ---
            try:
                # Smart waiting: Try to detect content quickly
                page.wait_for_selector('article, .content, [class*="article"], body, [class*="content"], .post, .story', 
                                      timeout=3000, state='attached')
                content_load_time = time.time() - start_time
                print(f"✓ Content loaded in {content_load_time:.2f}s")
                
            except Exception as e:
                # Fallback: use domain-specific timing
                wait_time = get_domain_wait_time(url)
                page.wait_for_timeout(wait_time)
                fallback_time = time.time() - start_time
                print(f"⚠ Timed wait fallback: {fallback_time:.2f}s for {urlparse(url).netloc}")

            # --- RESOURCE OPTIMIZATION - NEW CODE ---
            try:
                page.evaluate("""
                    // Remove heavy elements that slow down rendering
                    const heavyElements = [
                        'iframe[src*="ad"]', 
                        'img[src*="banner"]',
                        'div[class*="ad"]',
                        'script[src*="track"]',
                        'div[class*="social"]',
                        'div[class*="share"]',
                        'div[class*="comment"]'
                    ];
                    
                    heavyElements.forEach(selector => {
                        document.querySelectorAll(selector).forEach(el => el.remove());
                    });
                    
                    // Stop animations that might interfere
                    document.querySelectorAll('*').forEach(el => {
                        el.style.animation = 'none';
                        el.style.transition = 'none';
                    });
                """)
            except:
                pass

            # --- COOKIE CONSENT HANDLING --- 
            # Define site-specific rules to accept cookies
            cookie_rules = {
                "20minutes.ma": "#didomi-notice-agree-button",  # Selector for the "Agree" button
                # Add rule for the site with "موافق" button
                "example.ma": "button:has-text('موافق'), [aria-label*='موافق'], .accept-cookies",
                # You can add more sites here later
            }

            # Get the current website's domain from the URL
            current_domain = urlparse(url).netloc.lower()

            # Check if we have a rule for this domain
            if current_domain in cookie_rules:
                selector = cookie_rules[current_domain]
                try:
                    # Wait for the button to be present and clickable, then click it
                    accept_button = page.wait_for_selector(selector, timeout=5000, state="visible")
                    if accept_button:
                        accept_button.click()
                        print(f"✓ Accepted cookies on {current_domain}")
                        page.wait_for_timeout(1000)
                except Exception as e:
                    print(f"⚠ Cookie button not found on {current_domain}: {e}")
                    pass
            
            # --- ADDITIONAL ARABIC SITE HANDLING ---
            # Special handling for Arabic sites with "موافق" button
            try:
                # Try to find and click any button with Arabic acceptance text
                arabic_accept_buttons = page.query_selector_all(
                    "button:has-text('موافق'), button:has-text('أوافق'), " +
                    "button:has-text('قبول'), [aria-label*='موافق'], " +
                    "[aria-label*='أوافق'], [aria-label*='قبول']"
                )
                
                for button in arabic_accept_buttons:
                    try:
                        if button.is_visible():
                            button.click()
                            print("✓ Clicked Arabic acceptance button (موافق)")
                            page.wait_for_timeout(1000)
                            break
                    except:
                        continue
            except Exception as e:
                print(f"⚠ Arabic button handling skipped: {e}")
            # --- END COOKIE HANDLING ---

            # Additional check for empty pages
            try:
                page.wait_for_load_state('networkidle', timeout=10000)
            except:
                print("Network idle timeout, continuing anyway")

            try:
                content_check = page.evaluate("""() => {
                    return document.body.textContent.trim().length > 0;
                }""")
                if not content_check:
                    print("⚠ Page appears empty, trying to reload...")
                    page.reload(timeout=30000)
                    page.wait_for_timeout(3000)
            except:
                pass

            # --- Enhanced popup handling ---
            try:
                page.evaluate("""
                    const popupSelectors = [
                        '.popup', '.modal', '.cookie-banner', '.gdpr', '.consent',
                        '.newsletter-popup', '.ml-popup', '#newsletter-popup',
                        '.subscribe-popup', '.popup-newsletter'
                    ];
                    
                    popupSelectors.forEach(selector => {
                        document.querySelectorAll(selector).forEach(el => {
                            el.style.display = 'none';
                            el.remove();
                        });
                    });

                    document.querySelectorAll('.close, .popup-close, [aria-label*="Close"], [aria-label*="Fermer"], [onclick*="close"]')
                        .forEach(btn => {
                            try { btn.click(); } catch(e) {}
                        });

                    document.querySelectorAll('.overlay, .modal-backdrop, .popup-overlay')
                        .forEach(el => {
                            el.style.display = 'none';
                            el.remove();
                        });
                """)
                
                close_buttons = page.query_selector_all("button:has-text('×'), button:has-text('Close'), button:has-text('Fermer'), [aria-label*='Close'], [aria-label*='Fermer']")
                for button in close_buttons:
                    try:
                        button.click()
                        page.wait_for_timeout(500)
                    except:
                        pass
            except Exception as e:
                print(f"Popup handling skipped: {e}")

            # --- Special case: AUJOURD'HUI LE MAROC newsletter popup ---
            try:
                if "aujourdhui" in url:
                    btn = page.query_selector("button.close")
                    if btn:
                        btn.click()
                        page.wait_for_timeout(500)
                        print("✓ Closed AUJOURD'HUI newsletter popup")
            except:
                pass

            # --- Enhanced background colors ---
            try:
                page.evaluate("""
                    document.body.style.background = 'white';
                    document.body.style.backgroundColor = 'white';
                    
                    document.querySelectorAll('div, section, article').forEach(el => {
                        if (window.getComputedStyle(el).backgroundColor === 'transparent' || 
                            window.getComputedStyle(el).backgroundColor === 'rgba(0, 0, 0, 0)') {
                            el.style.backgroundColor = 'white';
                        }
                    });
                """)
            except:
                pass

            os.makedirs(output_dir, exist_ok=True)
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"content_screenshot_{timestamp}.{format}"
            elif not filename.endswith(f'.{format}'):
                # Ensure filename has the correct extension
                filename = f"{os.path.splitext(filename)[0]}.{format}"
                
            screenshot_path = os.path.join(output_dir, filename)

            page.evaluate("""
                const hideSelectors = [
                    'header', 'footer', 'nav', 'aside', '.sidebar',
                    '.navbar', '.menu', '.advertisement', '.ads',
                    '.social-share', '.comments', '.related-posts',
                    '.newsletter', '.widget', '.banner', '.ad', '.sponsor',
                    '.share-buttons', '.comment-section', '.recommendations'
                ];
                hideSelectors.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => el.style.display = 'none');
                });
            """)

            page.wait_for_timeout(1000)

            # OPTIMIZED DETECTION ORDER - FAST FIRST
            content_element = None
            if selector:
                content_element = page.query_selector(selector)

            if not content_element:
                content_element = fast_article_detection(page, url)  # Fast detection first

            if not content_element:
                content_element = smart_article_detection(page, url)  # Then smart detection

            if not content_element:
                content_element = enhanced_content_detection(page, url)  # Then enhanced

            if content_element:
                try:
                    content_element.scroll_into_view_if_needed()
                    page.wait_for_timeout(500)
                    
                    # Configure screenshot options based on format
                    screenshot_options = {'path': screenshot_path}
                    if format != 'png':
                        screenshot_options['type'] = format
                        
                    content_element.screenshot(**screenshot_options)
                    print(f"✓ Article-only screenshot saved: {filename}")
                    # --- ADD TIMING METRICS ---
                    total_time = time.time() - start_time
                    print(f"✓ Total processing time: {total_time:.2f}s")
                    browser.close()
                    return screenshot_path
                except Exception as e:
                    print(f"⚠ Failed to screenshot content element: {e}")

            # --- Extra fallback for image-only articles ---
            if not content_element:
                try:
                    main_img = page.query_selector("article img, .post img, .entry-content img")
                    if main_img:
                        main_img.scroll_into_view_if_needed()
                        page.wait_for_timeout(500)
                        
                        # Configure screenshot options based on format
                        screenshot_options = {'path': screenshot_path}
                        if format != 'png':
                            screenshot_options['type'] = format
                            
                        main_img.screenshot(**screenshot_options)
                        print(f"✓ Image-only screenshot saved: {filename}")
                        # --- ADD TIMING METRICS ---
                        total_time = time.time() - start_time
                        print(f"✓ Total processing time: {total_time:.2f}s")
                        browser.close()
                        return screenshot_path
                except Exception as e:
                    print(f"⚠ Failed image-only fallback: {e}")

            # Fallback: full page screenshot
            # Configure screenshot options based on format
            screenshot_options = {
                'path': screenshot_path,
                'full_page': True
            }
            if format != 'png':
                screenshot_options['type'] = format
                
            page.screenshot(**screenshot_options)
            print(f"✓ Fallback full page screenshot saved: {filename}")
            # --- ADD TIMING METRICS ---
            total_time = time.time() - start_time
            print(f"✓ Total processing time: {total_time:.2f}s")
            browser.close()
            return screenshot_path

    except Exception as e:
        print(f"❌ Content screenshot failed for {url}: {e}")
        return None