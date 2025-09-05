# News Scraper & Screenshot Automation Tool
 
A comprehensive tool for scraping news articles from Moroccan/Arabic news websites and automating screenshot capture with advanced content detection.

## 📋 Features

- Multi-source News Scraping: Support for Hespress (AR/FR/EN) and Alyaoum24

- Smart Screenshot Capture: Advanced content detection optimized for Moroccan/Arabic sites

- Bulk Processing: CSV-based screenshot automation with parallel processing

- Graphical Interface: User-friendly PyQt5 GUI with real-time progress tracking

- API Integration: Fetch data directly from REST APIs

- Multiple Formats: Support for PNG, JPEG, and WebP image formats

- Domain Optimization: Custom selectors and timing for different websites

## 🚀 Installation
Clone the repository

```bash
git clone git@github.com:Adnane-markue/News.git
cd News
```
Install dependencies

```bash
pip install -r requirements.txt
```
## 🏗️ Project Structure
```
News/
├─ README.md
├─ requirements.txt
├─ run_scraper.py                  # CLI entry point
├─ src/
│  ├─ __init__.py
│  ├─ core/
│  │  ├─ base_scraper.py           # Generic scraping engine
│  │  ├─ api_client.py
│  │  └─ utils.py                  # Logging, robots.txt, cache helpers
│  └─ configs/
│     ├─ hespress_ar.yaml
│     ├─ hespress_fr.yaml
│     ├─ hespress_en.yaml
│     └─ alyaoum24.yaml
│  └─ tools/
│     ├─ csv_screenshots.py
│     ├─ screenshots.py
│     └─ ui.py
├─ data/
│  ├─ raw/                         # raw/{site}/{site.YYYYMMDD.json}
│  ├─ processed/                   # processed/{site}/classified/{category}/
│  └─ cache/                       # cache/{hash-of-url}
└─ logs/
```
## 🧩 The Scraper System
### Generic Scraping Architecture
The scraper uses a YAML-based configuration system that makes it highly flexible and extensible. Each website has its own configuration file in src/configs/ that defines how to scrape that particular site.

### How the Generic Scraper Works
1. Configuration-Driven: Each site has a YAML file defining:

- Navigation patterns

- Article selection rules

- Content extraction selectors

- Pagination handling

2. Base Scraper Engine: base_scraper.py provides:

- Common scraping functionality

- Request handling with retries

- HTML parsing utilities

- Data extraction framework

3. YAML Configuration Structure:

```yaml
site_name: "hespress_ar"
base_url: "https://www.hespress.com"
categories:
  economie:
    url_pattern: "/economie"
    selectors:
      articles: ".article-card"
      title: "h2 a"
      link: "h2 a@href"
      summary: ".excerpt"
pagination:
  type: "query_param"
  param: "page"
  start: 1
```
### Supported Configuration Options
#### Navigation & Structure:

- Category URL patterns

- Article container selectors

- Pagination handling (query params, next buttons, etc.)

#### Content Extraction:

- Title selectors

- Link extraction

- Summary/description

- Publication date

- Author information

- Category tags

#### Pagination Types:

- Query parameter pagination (?page=2)

- Path pagination (/page/2/)

- Next button navigation

- JavaScript-based loading


## 🎯 Usage

Graphical Interface
```bash
python -m src.tools.ui
```
Command Line Screenshot Tool
```bash
python -m src.tools.csv_screenshots articles.csv \
  --url-column lien_web \
  --filename-column id \
  --support-column support_titre \
  --batch-size 5 \
  --max-workers 3 \
  --delay 0.5 \
  --screenshot-type content \
  --image-format jpeg \
  --output-dir data/csv_screenshots_content
```
Command Line News Scraper
```bash
python run_scraper.py --site hespress_ar --categories economie sports --limit 10 --max-pages 2
``` 
```bash
python run_scraper.py --site hespress_ar --categories economie --limit 12 --max-pages 3
``` 
```bash
python run_scraper.py --site hespress_fr --categories economie sports --limit 8 --max-pages 2
``` 
```bash
python run_scraper.py --site hespress_en --categories politics --limit 6 --max-pages 2
```     
```bash
python run_scraper.py --site alyaoum24 --limit 10 --max-pages 1
``` 
## 🛠️ Configuration

### CSV Format Requirements
Your CSV file should include these columns:

- lien_web: URL to capture

- id: Unique identifier for filename

- support_titre: Category for organizing screenshots

### Supported Moroccan News Websites

The tool includes optimized selectors for these Moroccan news portals:

- **Regional News**: `icirabat.com`, `icinador.com`, `icimeknes.com`
- **City Portals**: `icimarrakech.com`, `iciguercif.com`, `icifes.com`  
- **Local News**: `icidakhla.com`, `icicasa.com`, `iciagadir.com`
- **Media Networks**: `ichrakanews.com`, `i3lamtv.com`, `i3lam24.com`

And many more Moroccan/Arabic news sites with specialized content detection patterns.

## ⚙️ Advanced Options
### Scraper Parameters
`--site`: Which website configuration to use

`--categories`: Specific categories to scrape

`--limit`: Maximum number of articles to fetch

`--max-pages`: Maximum pages to crawl per category

### Screenshot Types
`fullpage`: Full webpage screenshot

`content`: Article content only (smart detection)

`both`: Both fullpage and content screenshots

### Image Formats
`png`: Lossless format, best for text

`jpeg`: Compressed format, smaller file size

`webp`: Modern format, good compression

### Performance Tuning
`--max-workers`: Number of parallel browsers (3-5 recommended)

`--delay`: Delay between requests to avoid rate limiting

`--batch-size`: Process in smaller batches for stability

## 🎯 Smart Content Detection
The tool uses multiple strategies to find article content:

1. Domain-specific selectors: Pre-configured for known sites

2. Generic patterns: Common article/content selectors

3. Aggressive detection: Text density and paragraph counting

4. Fallback methods: Full-page capture when content detection fails

## 📊 Output
### Scraper Output
```batch
data/
├─ raw/
│  └─ hespress_ar/
│     └─ hespress_ar.20231201.json
├─ processed/
│  └─ hespress_ar/
│     └─ classified/
│        └─ economie/
│           └─ article_data.json
```
### Screenshot Output
```batch
data/
├─ csv_screenshots/                # Default output directory
│  ├─ website_name/                # Organized by support_titre
│  │  ├─ fullpage/                 # Full page screenshots
│  │  └─ content/                  # Content-only screenshots
│  └─ screenshot_results_TIMESTAMP.csv  # Processing metadata
```
#### The results CSV includes:

- Original URL and metadata

- Screenshot file paths

- Success/failure status

- Processing time

- Error messages (if any)

## 🔧 Troubleshooting
### Common Scraper Issues
1. Website structure changes: Update YAML selectors

2. Pagination failures: Check pagination configuration

3. Rate limiting: Increase delays between requests

### Common Screenshot Issues
1. Timeout errors: Increase delay or reduce max-workers

2. Empty screenshots: Check if website requires JavaScript

3. Popup interference: The tool automatically handles common popups

### Performance Tips
- Use --delay 1.0 for more reliable results

- Start with small --batch-size for testing

- Monitor memory usage with high --max-workers

## 🤝 Contributing
1. Add new websites: Create YAML configs in src/configs/

2. Improve selectors: Update existing configurations

3. Add features: Extend the base scraper or UI

4. Test thoroughly: Ensure compatibility with existing functionality

#### Contribution Process
1. Fork the repository

2. Create a feature branch

3. Add tests for new functionality

4. Submit a pull request

## 🆘 Support
For issues and questions:

Check the troubleshooting section above

Review the example commands

Ensure all dependencies are installed

Verify YAML configuration syntax

### Happy scraping! 🚀