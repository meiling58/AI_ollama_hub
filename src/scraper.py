import datetime
import json
import csv
import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class OllamaScraper:
    # Define this at the top, so it's easy to update
    KNOWN_CAPABILITIES = {'vision', 'tools', 'cloud', 'thinking', 'embedding'}

    def __init__(self, headless=False):
        options = Options()
        if headless:
            options.add_argument("--headless")
        self.driver = webdriver.Firefox(options=options)
        self.base_url = "https://ollama.com/library"
        self.wait = WebDriverWait(self.driver, 10)
        # Selectors converted from your Robot variables
        self.models_xpath = '//*[@id="repo"]/ul/li'  # Container for the list items
        self.name_subpath = './/h2/div/span'  # Relative path for the name

    def open_library(self):
        self.driver.get(self.base_url)
        self.driver.maximize_window()
        self.wait.until(EC.presence_of_element_located((By.ID, "repo")))

    def scroll_to_bottom(self):
        print("Scrolling to load all models...")
        last_count = 0

        while True:
            # Get all current model items
            current_models = self.driver.find_elements(By.XPATH, self.models_xpath)
            current_count = len(current_models)

            # If count hasn't changed, we likely hit the bottom
            if current_count == last_count:
                break

            last_count = current_count
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

            # SMART WAIT: Wait until the number of list items is greater than our last count
            try:
                # We wait up to 5 seconds for at least one new model to appear
                WebDriverWait(self.driver, 5).until(
                    lambda d: len(d.find_elements(By.XPATH, self.models_xpath)) > current_count
                )
            except:
                # If no new models appear within 5 seconds, assume we are at the end
                print("Reached the end of the library.")
                break

    def get_all_models(self):
        self.scroll_to_bottom()
        model_elements = self.driver.find_elements(By.XPATH, self.models_xpath)
        model_count = len(model_elements)  # Count the number of elements
        model_names = []
        for element in model_elements:
            try:
                name = element.find_element(By.XPATH, self.name_subpath).text
                model_names.append(name)
            except Exception as e:
                continue

        return model_count, model_names

    def get_model_tag_details(self, model_name):
        url = f"{self.base_url}/{model_name}/tags"
        self.driver.get(url)

        result = []

        # Wait until first data row appears
        try:
            self.wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.grid.grid-cols-12.items-center span.col-span-6 a")
                )
            )
        except:
            print(f"⚠ Timed out waiting for tag rows for {model_name}")
            return result

        # Find all data rows
        rows = self.driver.find_elements(
            By.CSS_SELECTOR, "div.grid.grid-cols-12.items-center"
        )

        for row in rows:
            # Skip header row
            if "bg-neutral-50" in row.get_attribute("class"):
                continue

            # Version name
            try:
                version = row.find_element(
                    By.CSS_SELECTOR, "span.col-span-6 a"
                ).text.strip()
            except:
                continue

            # Size and Context → <p class="col-span-2">
            p_cols = row.find_elements(By.CSS_SELECTOR, "p.col-span-2")
            size = p_cols[0].text.strip() if len(p_cols) > 0 else ""
            context = p_cols[1].text.strip() if len(p_cols) > 1 else ""

            # Input → <div class="col-span-2">
            d_cols = row.find_elements(By.CSS_SELECTOR, "div.col-span-2")
            input_type = d_cols[-1].text.strip() if d_cols else ""

            # Updated at → next sibling div after the grid row
            # Text looks like "6995872bfe4c · 9 months ago"
            try:
                sibling = row.find_element(
                    By.XPATH, "following-sibling::div[1]"
                )
                raw = sibling.text.replace('\xa0', ' ').strip()
                # Extract just "X months/years ago" — split on " · "
                if '·' in raw:
                    updated_at = raw.split('·')[-1].strip()
                else:
                    updated_at = raw
            except:
                updated_at = None

            if version:
                result.append({
                    "name": version,
                    "size": size,
                    "context": context,
                    "input": input_type,
                    "usage_command": f"ollama pull {version}",
                    "updated_at": updated_at
                })

        return result

    def get_all_models_info(self):
        self.scroll_to_bottom()

        # Target the list items
        model_cards = self.driver.find_elements(By.XPATH, '//*[@id="repo"]/ul/li')

        # ── STEP 1: Collect basic info from all cards FIRST (don't navigate away) ──
        basic_info_list = []
        for card in model_cards:
            try:
                name = card.find_element(By.XPATH, './/h2/div/span').text
                summary = card.find_element(By.XPATH, './/p').text

                metadata1 = card.find_elements(By.XPATH, './/div[contains(@class, "flex")]/div/span')
                data = [span.text for span in metadata1 if span.text.strip()]
                capabilities = [cap for cap in data if cap in self.KNOWN_CAPABILITIES]
                versions = [v for v in data if v not in self.KNOWN_CAPABILITIES]

                for item in data:
                    if item not in self.KNOWN_CAPABILITIES and not any(
                            char.isdigit() for char in item) and item != 'latest':
                        print(f"DEBUG: Found potential new capability tag: {item}")

                primary_version = versions[0] if versions else "latest"

                meta_spans_3 = card.find_elements(By.XPATH, './/div[contains(@class, "flex")]/p/span')
                metadata = [(span.text).replace('\n', '') for span in meta_spans_3 if span.text.strip()]

                basic_info_list.append({
                    "model_name": name,
                    "primary_version": primary_version,
                    "capabilities": capabilities,
                    "metadata": metadata,
                    "summary": summary,
                    "usage_command": f"ollama run {name}:{primary_version}",
                    "url": f"https://ollama.com/library/{name}",
                    "updated_at": metadata[2] if len(metadata) > 2 else "Unknown",
                })
            except Exception as e:
                print(f"Error collecting basic info: {e}")
                continue

        print(f"✅ Collected basic info for {len(basic_info_list)} models")

        # ── STEP 2: Visit each model's tags page to get version details ──
        results = []
        for i, info in enumerate(basic_info_list):
            name = info["model_name"]
            print(f"  [{i + 1}/{len(basic_info_list)}] Fetching tags for {name}...")
            try:
                versions = self.get_model_tag_details(name)
            except Exception as e:
                print(f"  ⚠ Failed to get tags for {name}: {e}")
                versions = []

            results.append({
                **info,
                "versions": versions,
            })

        print(f"✅ Done! Collected full details for {len(results)} models")
        return results

    def save_data(self, data):
        timestamp = datetime.datetime.now().strftime("%Y%m%d")

        # Create output folder if it doesn't exist
        data_path = os.path.dirname(os.getcwd())
        data_dir = os.path.join(data_path, "data")
        os.makedirs(data_dir, exist_ok=True)

        # Save JSON
        with open(f'{data_dir}/ollama_library.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        # Save CSV
        if data:
            keys = data[0].keys()
            with open(f'{data_dir}/ollama_library.csv', 'w', newline='', encoding='utf-8') as f:
                dict_writer = csv.DictWriter(f, fieldnames=keys)
                dict_writer.writeheader()
                dict_writer.writerows(data)

        print(f"Successfully archived {len(data)} models.")

    def close(self):
        self.driver.quit()


if __name__ == "__main__":
    scraper = OllamaScraper(headless=False)
    try:
        scraper.open_library()
        # all_models = scraper.get_all_models()
        # print(f"Total models found: {all_models[0]}")
        # print(f"Model names: {all_models[1][:10]}")  # Print first 10 model names for verification
        data = scraper.get_all_models_info()
        scraper.save_data(data)
    finally:
        scraper.close()
