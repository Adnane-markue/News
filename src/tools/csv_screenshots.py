import pandas as pd
import os
import sys
import time
import re
import argparse
import threading
from typing import List, Optional, Deque, Callable
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque
from urllib.parse import urlparse

# Add src/ to Python path to import the screenshot function
HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(HERE, '..')
sys.path.insert(0, SRC_DIR)

from src.tools.screenshots import take_screenshot, take_content_screenshot

def sanitize_filename(value: str) -> str:
    """Make filename safe for filesystem"""
    return re.sub(r'[^\w\-.]', '_', str(value))


def get_progress_interval(batch_size: int) -> int:
    """Automatically determine progress interval based on batch size."""
    if batch_size <= 50:
        return 1
    elif batch_size <= 500:
        return 10
    elif batch_size <= 5000:
        return 50
    else:
        return 100


def round_robin_rows(df: pd.DataFrame, url_column: str, support_column: Optional[str] = None) -> pd.DataFrame:
    """
    Interleave rows by support_column (or domain if missing):
    x0, y0, z0, x1, y1, z1, ...
    """
    df = df.copy()
    
    if support_column and support_column in df.columns:
        df["__group__"] = df[support_column].fillna("__unknown__")
    else:
        df["__group__"] = df[url_column].apply(
            lambda x: urlparse(str(x)).netloc if isinstance(x, str) and "://" in str(x) else "__unknown__"
        )
    
    groups = [g.index.tolist() for _, g in df.groupby("__group__")]
    iters = [iter(g) for g in groups]
    ordered_indices = []

    while iters:
        new_iters = []
        for it in iters:
            try:
                ordered_indices.append(next(it))
                new_iters.append(it)
            except StopIteration:
                pass
        iters = new_iters

    return df.loc[ordered_indices].drop(columns=["__group__"])

def get_domain_selector(url: str) -> Optional[str]:
    """Return a content selector for the URL's domain if available"""
    from src.tools.screenshots import DOMAIN_SELECTORS
    domain = urlparse(url).netloc
    selectors = DOMAIN_SELECTORS.get(domain)
    if selectors:
        return ", ".join(selectors)  # Convert list to comma-separated string
    return None

def take_article_only(url: str, output_dir: str, filename: str, selector: Optional[str] = None) -> Optional[str]:
    """
    Take article-only screenshot for Moroccan/Arabic news sites.
    Optimized but keeps general Moroccan selectors as fallback.
    """
    from src.tools.screenshots import take_content_screenshot

    # 1. Use provided selector first (highest priority - from command line)
    if selector:
        content_path = take_content_screenshot(url, output_dir, filename, selector=selector)
        if content_path:
            print(f"✓ Article-only screenshot saved using provided selector: {selector}")
            return content_path

    # 2. Try domain-specific selectors from unified DOMAIN_SELECTORS
    domain_selector = get_domain_selector(url)
    if domain_selector:
        content_path = take_content_screenshot(url, output_dir, filename, selector=domain_selector)
        if content_path:
            print(f"✓ Article-only screenshot saved using domain selector: {domain_selector}")
            return content_path

    # 3. KEEP THIS: General Moroccan/Arabic selectors (excellent fallback)
    selectors = [
        'article', '.details-content', '.news-details', '.news-body',
        '.article-body', '.post-content', '.story-content'
    ]

    for sel in selectors:
        content_path = take_content_screenshot(url, output_dir, filename, selector=sel)
        if content_path:
            print(f"✓ Article-only screenshot saved using general selector: {sel}")
            return content_path  # return immediately when successful

    # 4. Final fallback: smart detection (no selector - uses fast detection internally)
    content_path = take_content_screenshot(url, output_dir, filename)
    if content_path:
        print("✓ Article-only screenshot saved using smart detection")
    return content_path



def process_chunk(
    chunk: pd.DataFrame,
    url_column: str,
    output_dir: str,
    filename_column: Optional[str],
    support_column: Optional[str],  # support_titre column
    delay: float,
    max_workers: int,
    time_window: Deque[float],
    total_estimated_rows: int,
    global_processed: List[int],
    global_success: List[int],
    screenshot_type: str,
    content_selector: Optional[str] = None,
    progress_interval: Optional[int] = None,
    progress_callback: Optional[Callable] = None  # ADD THIS
) -> List[dict]:
    """Process a chunk of the CSV file with accurate ETA calculation."""
    
    results = []
    processed_in_chunk = 0
    success_in_chunk = 0
    lock = threading.Lock()

    if not progress_interval:
        progress_interval = get_progress_interval(len(chunk))

    # domain lock helpers
    domain_locks = {}
    domain_locks_guard = threading.Lock()

    def get_domain(u: str) -> str:
        try:
            return urlparse(u).netloc or "unknown"
        except Exception:
            return "unknown"

    def acquire_domain_lock(domain: str) -> threading.Semaphore:
        with domain_locks_guard:
            lock = domain_locks.get(domain)
            if lock is None:
                lock = threading.Semaphore(1)  # one concurrent request per domain
                domain_locks[domain] = lock
            return lock

    def worker(row):
        nonlocal processed_in_chunk, success_in_chunk

        url = row[url_column]
        elapsed = 0
        result = {**row.to_dict(),
                  "screenshot_path": None,
                  "content_screenshot_path": None,
                  "screenshot_taken_at": None,
                  "screenshot_success": False,
                  "content_screenshot_success": False,
                  "processing_time": None,  # NEW: Track processing time
                  "domain": None}           # NEW: Track domain

        # ensure variables are defined
        screenshot_path = None
        content_path = None

        start_time = time.time()

        if pd.notna(url) and isinstance(url, str) and url.startswith(('http://', 'https://')):
            # NEW: Extract domain for tracking
            domain = get_domain(url)
            result["domain"] = domain
            # Generate filename
            if filename_column and filename_column in row and pd.notna(row[filename_column]):
                base_filename = sanitize_filename(row[filename_column])
                filename = f"{base_filename}.png"
            else:
                from hashlib import md5
                url_hash = md5(url.encode()).hexdigest()[:12]
                filename = f"screenshot_{url_hash}.png"

            # output directory (support_titre subfolders if needed)
            final_output_dir = output_dir
            if support_column and support_column in row and pd.notna(row[support_column]):
                website_name = sanitize_filename(row[support_column])
                website_dir = os.path.join(output_dir, website_name)
                os.makedirs(website_dir, exist_ok=True)
                final_output_dir = website_dir

            # Get selector for domain if exists
            domain_selector = get_domain_selector(url)

            # domain lock
            domain = get_domain(url)
            dlock = acquire_domain_lock(domain)
            with dlock:
                try:
                    if screenshot_type == 'fullpage':
                        screenshot_path = take_screenshot(url, final_output_dir, filename)
                        content_path = None

                    elif screenshot_type == 'content':
                        content_path = take_article_only(url, final_output_dir, filename, selector=domain_selector)
                        screenshot_path = None  # full page not taken

                    elif screenshot_type == 'both':
                        fullpage_dir = os.path.join(final_output_dir, 'fullpage')
                        content_dir = os.path.join(final_output_dir, 'content')
                        os.makedirs(fullpage_dir, exist_ok=True)
                        os.makedirs(content_dir, exist_ok=True)

                        screenshot_path = take_screenshot(url, fullpage_dir, filename)
                        content_path = take_article_only(url, content_dir, filename, selector=domain_selector)

                    # Update result
                    elapsed = time.time() - start_time
                    result.update({
                        "screenshot_path": screenshot_path,
                        "content_screenshot_path": content_path,
                        "screenshot_taken_at": datetime.now().isoformat(),
                        "screenshot_success": screenshot_path is not None,
                        "content_screenshot_success": content_path is not None,
                        "processing_time": elapsed  # NEW: Store processing time
                    })

                    success_types = []
                    if screenshot_path:
                        success_types.append("fullpage")
                    if content_path:
                        success_types.append("content")

                    if success_types:
                        print(f"✔ Processed {url} → {', '.join(success_types)} in {elapsed:.2f}s")
                    else:
                        print(f"⚠ Failed {url} in {elapsed:.2f}s")

                except Exception as e:
                    elapsed = time.time() - start_time
                    print(f"⚠️ Error screenshotting {url}: {e}")

        with lock:
            processed_in_chunk += 1
            if result["screenshot_success"] or result["content_screenshot_success"]:
                success_in_chunk += 1

            global_processed[0] += 1
            if result["screenshot_success"] or result["content_screenshot_success"]:
                global_success[0] += 1

            # ADD PROGRESS CALLBACK HERE
            if progress_callback:
                progress_callback(global_processed[0], total_estimated_rows, global_success[0])

            if elapsed > 0:
                time_window.append(elapsed)

            if time_window:
                avg_time = sum(time_window) / len(time_window)
                remaining = total_estimated_rows - global_processed[0]
                eta_seconds = remaining * avg_time

                if processed_in_chunk % progress_interval == 0 or processed_in_chunk == len(chunk):
                    print(f"Progress: {global_processed[0]}/{total_estimated_rows} | "
                          f"Success: {global_success[0]} | Fail: {global_processed[0] - global_success[0]} | "
                          f"ETA: {eta_seconds / 60:.2f} min")

        if delay > 0:
            time.sleep(delay)

        return result

    results_list = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(worker, row): row for _, row in chunk.iterrows()}
        for future in as_completed(futures):
            results_list.append(future.result())

    return results_list



def estimate_total_rows(csv_path: str, url_column: str, chunksize: int, already_done: set) -> int:
    """Estimate total rows without loading entire CSV into memory."""
    total = 0
    for chunk in pd.read_csv(csv_path, usecols=[url_column], chunksize=chunksize):
        if already_done:
            chunk = chunk[~chunk[url_column].astype(str).isin(already_done)]
        total += len(chunk)
    return total


def process_csv_screenshots(
    csv_path: str,
    url_column: str = 'url',
    output_dir: str = 'data/csv_screenshots',
    filename_column: Optional[str] = None,
    support_column: Optional[str] = None,
    batch_size: Optional[int] = None,
    delay: float = 1.0,
    chunksize: int = 1000,
    max_workers: int = 3,
    resume: bool = False,
    screenshot_type: str = 'fullpage',
    content_selector: Optional[str] = None,
    progress_interval: Optional[int] = None,
    start_row: int = 0,
    progress_callback: Optional[Callable] = None  # ADD THIS
) -> str:
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_csv_path = os.path.join(output_dir, f"screenshot_results_{timestamp}.csv")

    already_done = set()
    if resume:
        existing_files = sorted([f for f in os.listdir(output_dir) if f.startswith("screenshot_results_")])
        for f in existing_files:
            try:
                existing_df = pd.read_csv(os.path.join(output_dir, f))
                if filename_column and filename_column in existing_df.columns:
                    already_done |= set(existing_df[filename_column].dropna().astype(str).tolist())
                else:
                    already_done |= set(existing_df[url_column].dropna().astype(str).tolist())
            except Exception as e:
                print(f"⚠️ Could not load results from {f}: {e}")

    print("Estimating total rows to process...")
    total_estimated_rows = estimate_total_rows(csv_path, url_column, chunksize, already_done)
    if batch_size:
        total_estimated_rows = min(total_estimated_rows, batch_size)
    print(f"Estimated total rows to process: {total_estimated_rows}")
    
    # ADD INITIAL PROGRESS CALLBACK
    if progress_callback:
        progress_callback(0, total_estimated_rows, 0)

    global_processed = [0]
    global_success = [0]
    time_window = deque(maxlen=50)
    t_start = time.time()

    for chunk in pd.read_csv(csv_path, chunksize=chunksize):
        if start_row > 0:
            if start_row >= len(chunk):
                start_row -= len(chunk)
                continue
            else:
                chunk = chunk.iloc[start_row:]
                start_row = 0

        if url_column not in chunk.columns:
            print(f"URL column '{url_column}' not found in CSV. Available: {list(chunk.columns)}")
            sys.exit(1)

        if already_done:
            if filename_column and filename_column in chunk.columns:
                chunk = chunk[~chunk[filename_column].astype(str).isin(already_done)]
            else:
                chunk = chunk[~chunk[url_column].astype(str).isin(already_done)]

        if chunk.empty:
            continue

        if batch_size and global_processed[0] >= batch_size:
            break

        if batch_size:
            remaining = batch_size - global_processed[0]
            chunk = chunk.head(remaining)

        print(f"\nProcessing rows {global_processed[0] + 1} → {global_processed[0] + len(chunk)}")

        # --- Apply round robin ordering ---
        chunk = round_robin_rows(chunk, url_column, support_column)

        results = process_chunk(
            chunk=chunk,
            url_column=url_column,
            output_dir=output_dir,
            filename_column=filename_column,
            support_column=support_column,
            delay=delay,
            max_workers=max_workers,
            time_window=time_window,
            total_estimated_rows=total_estimated_rows,
            global_processed=global_processed,
            global_success=global_success,
            screenshot_type=screenshot_type,
            content_selector=content_selector,
            progress_interval=progress_interval,
            progress_callback=progress_callback  # ADD THIS
        )

        results_df = pd.DataFrame(results)
        header = not os.path.exists(results_csv_path) or os.path.getsize(results_csv_path) == 0
        results_df.to_csv(results_csv_path, index=False, mode='a', header=header, encoding='utf-8')

    t_end = time.time()
    elapsed = t_end - t_start

    print(f"\n✅ Processing complete!")
    print(f"Captured {global_success[0]}/{global_processed[0]} screenshots successfully")
    
    # ADD FINAL PROGRESS CALLBACK
    if progress_callback:
        progress_callback(global_processed[0], total_estimated_rows, global_success[0])
    
    print(f"Results CSV saved to: {results_csv_path}")
    print(f"⏱ Total time taken: {elapsed:.2f} seconds ({elapsed/60:.2f} minutes)")

    # ADD PERFORMANCE ANALYSIS AT THE END
    try:
        # Analyze performance after completion
        results_df = pd.read_csv(results_csv_path)
        if 'processing_time' in results_df.columns and 'domain' in results_df.columns:
            print("\n📊 Performance Analysis:")
            domain_stats = results_df.groupby('domain').agg({
                'processing_time': ['mean', 'count']
            }).round(2)
            
            domain_stats.columns = ['avg_time_seconds', 'url_count']
            domain_stats = domain_stats.sort_values('avg_time_seconds', ascending=False)
            
            print("Slowest domains:")
            print(domain_stats.head(10))
            
            print(f"\nOverall average: {results_df['processing_time'].mean():.2f}s per URL")
    except Exception as e:
        print(f"⚠ Performance analysis skipped: {e}")

    return results_csv_path


def main():
    parser = argparse.ArgumentParser(description='Take screenshots from URLs in a CSV file')
    parser.add_argument('csv_file', help='Path to the CSV file containing URLs')
    parser.add_argument('--url-column', default='url', help='Column name containing URLs (default: "url")')
    parser.add_argument('--output-dir', default='data/csv_screenshots', help='Output directory for screenshots')
    parser.add_argument('--filename-column', help='Column to use for screenshot filenames')
    parser.add_argument('--support-column', help='Column to use for website classification (e.g., support_titre)')
    parser.add_argument('--batch-size', type=int, help='Number of URLs to process (optional)')
    parser.add_argument('--delay', type=float, default=1.0, help='Delay between screenshots in seconds (default: 1.0)')
    parser.add_argument('--no-delay', action='store_true', help='Disable delay between screenshots')
    parser.add_argument('--chunksize', type=int, default=1000, help='Number of rows per CSV chunk (default: 1000)')
    parser.add_argument('--max-workers', type=int, default=3, help='Number of parallel screenshot workers (default: 3)')
    parser.add_argument('--resume', action='store_true', help='Resume from all previous results CSVs if exist')
    parser.add_argument('--start-row', type=int, default=0, help='Row index to start processing from (0-based)')
    parser.add_argument('--screenshot-type', choices=['fullpage', 'content', 'both'], default='fullpage',
                       help='Type of screenshot to take: fullpage, content, or both')
    parser.add_argument('--content-selector', help='CSS selector for content area (e.g., "article, .content, main")')
    parser.add_argument('--progress-interval', type=int, help='Force progress reporting every N URLs (overrides auto)')

    args = parser.parse_args()
    delay = 0 if args.no_delay else args.delay

    try:
        process_csv_screenshots(
            csv_path=args.csv_file,
            url_column=args.url_column,
            output_dir=args.output_dir,
            filename_column=args.filename_column,
            support_column=args.support_column,
            batch_size=args.batch_size,
            delay=delay,
            chunksize=args.chunksize,
            max_workers=args.max_workers,
            resume=args.resume,
            screenshot_type=args.screenshot_type,
            content_selector=args.content_selector,
            progress_interval=args.progress_interval,
            start_row=args.start_row
        )
    except Exception as e:
        print(f"Error occurred: {e}")


if __name__ == '__main__':
    main()