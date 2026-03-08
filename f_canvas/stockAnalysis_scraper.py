import dotenv
import os

import pandas as pd

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException,
    NoSuchWindowException,
    NoAlertPresentException,
)
import time

dotenv.load_dotenv(
    # dotenv_path=dotenv_path,
    override=True,
    verbose=True,
)

# URL to scrape
url_login = "https://stockanalysis.com/login/"
# url = "https://stockanalysis.com/trending/"
url = "https://stockanalysis.com/markets/gainers/"

# Set up the webdriver (e.g., Chrome)
options = webdriver.ChromeOptions()
options.add_argument(
    "--disable-blink-features=AutomationControlled"
)  # Hide automation flag
driver = webdriver.Chrome(options=options)


try:
    # Navigate to the login page
    driver.get("https://stockanalysis.com/login/")

    # Wait for and fill email field
    email_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.NAME, "email"))  # Adjust if ID/class differs
    )
    email_input.send_keys(os.getenv("SA_EMAIL"))

    # Wait for and fill password field
    password_input = driver.find_element(By.NAME, "password")  # Adjust selector
    password_input.send_keys(os.getenv("SA_PASSWORD"))

    # Click the login button
    login_button = driver.find_element(
        By.XPATH, "//button[contains(text(), 'Log In')]"
    )  # Adjust
    login_button.click()

    # Wait for login to complete (e.g., check for a post-login element)
    time.sleep(3)  # Or use WebDriverWait for a specific element

    # Proceed with scraping or other actions
    print("Logged in successfully!")
except Exception as e:
    print("Errors from log in: {e}")


# Wait for login to complete (e.g., check for dashboard or error)
time.sleep(3)  # Or use WebDriverWait for a post-login element


driver.get(url)
tables_data = []
iteration = 0

while True:
    iteration += 1
    print(f"Iteration: {iteration} ... ...")

    # Wait for the pagination element to be present
    try:
        # Wait for the pagination element to load
        pagination_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, "//div[@class='flex items-center space-x-3']")
            )
        )

        # Get the inner HTML of the pagination element
        page_info = pagination_element.find_element(
            By.XPATH, ".//span[@class='whitespace-nowrap']"
        ).text

        # Extract current page and total pages
        current_page = int(page_info.split("Page")[1].split("of")[0].strip())
        total_pages = int(page_info.split("of")[1].strip())

        print(f"Current Page (from HTML): {current_page} / {total_pages}")
    except Exception as e:
        print(f"Errors from finding pagination element: {e}")

    try:
        # Wait for tables to load and extract them
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.TAG_NAME, "table"))
        )
        tables = driver.find_elements(By.TAG_NAME, "table")

        for table in tables:
            tables_data.append(table.get_attribute("outerHTML"))
    except Exception as e:
        print("Errors from extracting tables: {e}")

    try:
        # Find and click "Next" button
        next_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//span[text()='Next' and contains(@class, 'hidden sm:inline')]",
                )
            )
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
        time.sleep(1)
    except Exception as e:
        print(f"Errors from finding the Next button: {e}")

    try:
        # Attempt standard click
        next_button.click()
    except ElementClickInterceptedException:
        # Fallback to JavaScript click - when an random popup (window or alert)
        try:
            driver.execute_script("arguments[0].click();", next_button)
            print("Trying JavaScript click ...")
        except Exception as e:
            print("Both Standard and JavaScript Clicks failed!")
            break

        # Wait for page to load
        # WebDriverWait(driver, 10).until(EC.staleness_of(next_button))

    #
    if current_page == total_pages:
        try:
            # Wait for tables to load and extract them
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.TAG_NAME, "table"))
            )
            tables = driver.find_elements(By.TAG_NAME, "table")
            for table in tables:
                tables_data.append(table.get_attribute("outerHTML"))
        except Exception as e:
            print("Errors from extracting tables: {e}")
        finally:
            break

# Close the browser
driver.quit()

# Create an empty list to store the DataFrames
df_list = []

# Iterate through the HTML tables and convert each to a DataFrame
for html_table in tables_data:
    df = pd.read_html(html_table)[
        0
    ]  # [0] is used to select the first (and likely only) table from the HTML
    df_list.append(df)

data = (
    pd.concat(df_list, ignore_index=True)
    .drop_duplicates(subset=["Symbol"])
    .reset_index(drop=True)
)
# Possible page duplications from the same HTML page (Mostly page 1)


"""'
# Or save as a HTML table first then convert it to Pandas DataFrame 
# Save (append mode) tables to files
for table_html in tables_data:
    with open(f"table_tmp.html", "a", encoding="utf-8") as f:
        f.write(table_html)

df_list = pd.read_html("table_tmp.html")

data = pd.concat(df_list)
"""

"""
# HTML pagination element, displays as "Page 1 of 23"

<div class="flex items-center space-x-3"><span class="whitespace-nowrap"><span class="hidden sm:inline" data-svelte-h="svelte-16pbjbl">Page</span> 1 of 23</span> <div class="relative inline-block text-left"><button class="controls-btn"><span class="truncate">20 Rows</span> <svg class="-mr-1 ml-1 h-5 w-5 xs:ml-2 undefined" viewBox="0 0 20 20" fill="currentColor" style="max-width:40px" aria-hidden="true"><path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"></path></svg></button> </div></div>


# HTML "Next" page control button

<button class="controls-btn xs:pl-1 xs:pr-1.5 bp:text-sm sm:pl-3 sm:pr-1"><span class="hidden sm:inline" data-svelte-h="svelte-1hxgo6f">Next</span> <svg class="-mb-px h-5 w-5 text-gray-600 bp:ml-1" viewBox="0 0 20 20" fill="currentColor" style="max-width:40px" aria-hidden="true"><path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd"></path></svg></button>
"""


'''

# This version is not stable

import os
import psutil
import random

from selenium import webdriver
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
    WebDriverException
)
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import pandas as pd
import time

import logging
# logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Base URL
base_url = "https://stockanalysis.com/trending/"
# The page at https://stockanalysis.com/trending/ likely uses JavaScript to load the pagination element dynamically, which is common for modern web applications.
# to open a chrome browser from a terminal, $ google-chrome


# Clean up any existing ChromeDriver processes
def kill_chromedriver():
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] in ['chromedriver', 'chromedriver.exe']:
            try:
                proc.kill()
                print(f"Killed existing ChromeDriver process (PID: {proc.pid})")
            except psutil.NoSuchProcess:
                pass


# Initialize Chrome WebDriver
try:
    kill_chromedriver()  # Clean up before starting
    # Set up Chrome options
    options = Options()
    options.add_argument("--headless=new")  # New headless mode
    options.add_argument("--no-sandbox")  # Required for Linux
    options.add_argument("--disable-dev-shm-usage")  # Avoid shared memory issues
    options.add_argument("--disable-gpu")  # Disable GPU
    options.add_argument("--remote-debugging-port=9222")  # Avoid port conflicts
    options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    # Specify ChromeDriver path (replace with actual path or use ChromeDriverManager)
    # Example manual path: "/usr/local/bin/chromedriver"
    # Using ChromeDriverManager for automatic download
    chromedriver_path = ChromeDriverManager().install()  # Automatically downloads correct version
    # If manual path is needed, uncomment and set:
    # chromedriver_path = "/path/to/chromedriver"  # e.g., "/usr/local/bin/chromedriver"

    # Verify ChromeDriver exists
    if not os.path.exists(chromedriver_path):
        print(f"ChromeDriver not found at {chromedriver_path}")
        exit()

    # Initialize WebDriver with Service
    service = Service(executable_path=chromedriver_path, port=9516)
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(30)

except WebDriverException as e:
    print(f"Failed to initialize ChromeDriver: {e}")
    print("Ensure Chrome is installed and compatible with ChromeDriver.")
    exit(1)


def scrape_page():
    """"
    Function to scrape a single page with a single table
    Example:
    base_url = "https://stockanalysis.com/ipos/"
    driver.get(base_url)
    tb_headers, tb_rows = scrape_page()
    df = pd.DataFrame(tb_rows, columns=tb_headers)
    """
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
    # Get page source after JavaScript rendering
    soup = BeautifulSoup(driver.page_source, "html.parser")
    
    # Find the table
    table = soup.find("table")

    if not table:
        print("No table found on the current page")
        return None, None
    
    # Extract headers (only on the first page)
    page_headers = [th.text.strip() for th in table.find_all("th")]
    
    # Extract rows
    page_rows = []
    for tr in table.find_all("tr")[1:]:  # Skip header row
        cells = [td.text.strip() for td in tr.find_all("td")]
        if cells:  # Only append non-empty rows
            page_rows.append(cells)
    
    return page_headers, page_rows


# 
def scrape_page_mtb():
    """
    Function to scrape a single page with more than one table, all have the same columns/fields.

    Example:
    # Get schedule IPO stocks in two weeks 
    base_url = "https://stockanalysis.com/ipos/calendar/"
    driver.get(base_url)
    tb_headers, tb_rows = scrape_page_mtb()
    df = pd.DataFrame(tb_rows, columns=tb_headers)
"""
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
    # Get page source after JavaScript rendering
    soup = BeautifulSoup(driver.page_source, "html.parser")
    
    # Find all tables
    tables = soup.find_all('table')
    if not tables:
        print("No tables found on the page.")
        exit()
    
    # Function to extract headers from a table
    def get_table_headers(table):
        headers = []
        header_row = table.find('tr')  # Assume first row contains headers
        if header_row:
            headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
        return headers

    # Function to extract table data as a list of lists
    def get_table_data(table):
        data = []
        rows = table.find_all('tr')[1:]  # Skip header row
        for row in rows:
            cells = [td.get_text(strip=True) for td in row.find_all(['td', 'th'])]
            if cells:  # Only add non-empty rows
                data.append(cells)
        return data


    # Get headers of the first table as reference
    reference_headers = get_table_headers(tables[0]) if tables else []
    if not reference_headers:
        print("No headers found in the first table.")
        exit()

    # Collect data from tables with matching headers
    all_data = []
    for table in tables:
        headers = get_table_headers(table)
        if headers == reference_headers:  # Check if headers match
            table_data = get_table_data(table)
            all_data.extend(table_data)
        else:
            print(f"Table skipped due to mismatched headers: {headers}")
    
    return reference_headers, all_data



# List to store all table data
all_rows = []
headers = []


# Navigate to the base URL
driver.get(base_url)
time.sleep(2)  # Wait for initial page load

# Scrape the first page
page_count = 1

with open(f"page_source{page_count}.html", "w", encoding="utf-8") as f:
    f.write(driver.page_source)




try:
    page_headers, page_rows = scrape_page()
except Exception as e:
    print(e)
    driver.quit()
    exit()
else:
    if page_headers and page_rows:
        headers = page_headers
        all_rows.extend(page_rows)
        print(f"{len(page_rows)} rows found on page: {page_count}, starting with {page_rows[0][1]}")

# Extract pagination information

# page info HTML element
# <span class="whitespace-nowrap"><span class="hidden sm:inline">Page</span> 1 of 110</span>
# Next page click HTML elemet:
# <button class="controls-btn xs:pl-1 xs:pr-1.5 bp:text-sm sm:pl-3 sm:pr-1"><span class="hidden sm:inline">Next</span> <svg class="-mb-px bp:ml-1" viewBox="0 0 20 20" fill="currentColor" style="max-width:40px" aria-hidden="true"><path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd"></path></svg></button>
while True:
    page_count += 1

    ## Find the clickable "Next" element
    try:
        #next_button = WebDriverWait(driver, 10).until(
        #    EC.element_to_be_clickable((By.XPATH, '//span[@class="hidden sm:inline" and contains(text(), "Next")]'))
        #    )
        # If the hidden sm:inline classes change dynamically, consider using the data-svelte-h attribute for the "Next" button: Confirmed by Grok
        next_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//span[@data-svelte-h="svelte-1hxgo6f"]'))
)
    except Exception as e:
        print(f"Exception from Find the clickable 'Next' element: {e}")
        break
    
    if (not next_button.is_enabled()) or ("disabled" in next_button.get_attribute("class")):
        print("No more pages to scrape. Stopping.")
        break
     
    time.sleep(random.uniform(2, 4))  # Wait for the next page to load

    ## Click and Scrap
    # Attempt standard click
    try:
        next_button.click()
        print("Clicked the Next button (standard click).")
    except Exception:
        print("Standard click intercepted. Trying JavaScript click...")
        # Fallback to JavaScript click
        try:
            driver.execute_script("arguments[0].click();", next_button)
            print("Clicked the Next button (JavaScript click).")
            time.sleep(2)  # Wait for page to load after click
        except Exception as e:
            print(f"Exception from JavaScript click: {e}")
            break
    finally:
        # Scrape the new page
        page_headers, page_rows = scrape_page()

        if page_rows:
            all_rows.extend(page_rows)
            print(f"{len(page_rows)} rows found on page: {page_count}, starting with {page_rows[0][1]}")
        else:
            print(f"Scraping failed on page: {page_count}")
            break

# Close the driver
try:
    driver.quit()
    print("Browser closed successfully.")
    kill_chromedriver()  # Clean up after closing
except WebDriverException as e:
    print(f"Error closing browser: {e}")

# Create a DataFrame
df = pd.DataFrame(all_rows, columns=headers)

# Save to CSV
df.to_csv("stock_gainers_all_pages.csv", index=False)
print(f"Scraped {page_count} pages and saved as stock_gainers_all_pages.csv")



'''
