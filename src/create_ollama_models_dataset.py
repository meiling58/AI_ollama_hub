"""
This script uses the OllamaScraper class to scrape information about all models available in the Ollama library. It opens the library page, retrieves the model information, and saves it to a file. The scraper runs in headless mode, meaning it operates without opening a visible browser window.
Finally, it ensures that the browser is closed after the scraping process is complete.
Store the scraped data in both JSON and CSV formats for easy access and analysis.
The output files are saved in a "data" directory.
- New file is created if it doesn't already exist.
- Updated the new data if file existed
"""

from scraper import OllamaScraper

if __name__ == "__main__":
    scraper = OllamaScraper(headless=True)
    try:
        scraper.open_library()
        data = scraper.get_all_models_info()
        scraper.save_data(data)
    finally:
        scraper.close()
        
