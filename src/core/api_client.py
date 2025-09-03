import requests
from typing import List, Dict
import logging
import time
from tenacity import retry, stop_after_attempt, wait_exponential

class NewsAPIClient:
    def __init__(self, api_url: str = "http://localhost:8000/v1/data/raw/news"):
        self.base_url = api_url
        self.batch_url = f"{api_url}/store_batch"
        self.logger = logging.getLogger(__name__)
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def send_batch(self, articles: List[Dict], batch_size: int = 100) -> Dict:
        """Send articles in configurable batches"""
        results = {"inserted": 0, "duplicates": 0, "failed": 0, "batches": 0}
        batch_times = []  # Track batch performance
        
        for i in range(0, len(articles), batch_size):
            batch = articles[i:i + batch_size]
            batch_start = time.time()
            
            try:
                response = requests.post(
                    self.batch_url,
                    json=batch,
                    timeout=30
                )
                response.raise_for_status()
                
                batch_result = response.json()
                results["inserted"] += batch_result.get("inserted", 0)
                results["duplicates"] += batch_result.get("duplicates", 0)
                results["failed"] += batch_result.get("failed", 0)
                results["batches"] += 1
                
                batch_time = time.time() - batch_start
                batch_times.append(batch_time)
                
                self.logger.info(
                    f"Batch {i//batch_size + 1}: {batch_result} "
                    f"in {batch_time:.2f}s "
                    f"({len(batch)/batch_time:.1f} articles/sec)"
                )
                
            except Exception as e:
                results["failed"] += len(batch)
                batch_time = time.time() - batch_start
                self.logger.error(f"Batch {i//batch_size + 1} failed in {batch_time:.2f}s: {str(e)}")
        
        # Log overall performance
        if batch_times:
            avg_batch_time = sum(batch_times) / len(batch_times)
            self.logger.debug(f"Average batch time: {avg_batch_time:.2f}s")
        
        return results
    
    def send_article(self, article_data: Dict) -> bool:
        """Single article fallback"""
        try:
            response = requests.post(
                f"{self.base_url}/store",
                json=article_data,
                timeout=10
            )
            response.raise_for_status()
            return True
        except Exception as e:
            self.logger.error(f"Single article failed: {str(e)}")
            return False