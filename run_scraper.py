import os
import sys

# Add src/ to Python path
HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(HERE, 'src')
sys.path.insert(0, SRC_DIR)

from src.core.base_scraper import GenericNewsScraper, build_arg_parser

# Configs directory
DEFAULT_CFG_DIR = os.path.join(SRC_DIR, 'configs')

if __name__ == '__main__':
    args = build_arg_parser().parse_args()

    if args.config:
        cfg_path = args.config
    else:
        if not args.site:
            print('Provide --site <key> or --config path to a YAML config')
            sys.exit(1)
        cfg_path = os.path.join(DEFAULT_CFG_DIR, f'{args.site}.yaml')
        if not os.path.exists(cfg_path):
            print(f'Config not found: {cfg_path}')
            sys.exit(1)

    scraper = GenericNewsScraper(config_path=cfg_path, data_dir=args.data_dir, logs_dir=args.logs_dir, enable_api=not args.disable_api)
    collected = scraper.run(categories=args.categories, limit=args.limit, max_pages=args.max_pages)

    print(f"Scraped {len(collected)} articles.")
