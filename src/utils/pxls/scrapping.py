from selenium import webdriver

# from selenium.webdriver.common.by import By
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

URL = "https://pxls.space/stats/"


def init_driver():
    # options to hide useless logs/ UI
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--log-level=3")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])

    driver = webdriver.Chrome(options=options)
    # driver.wait = WebDriverWait(driver, 5)
    # driver.implicitly_wait(5) # seconds
    return driver


def get_page_source(driver):
    # waiting for page to load
    driver.get(URL)
    # element = WebDriverWait(driver, 0.9).until(
    #     EC.presence_of_element_located(
    #         (By.XPATH, '//*[@id="tblGeneralStats"]/tbody/tr[5]/td[1]')
    #     )
    # )
    # driver.quit()
    return driver.page_source


def scrape_general_stats(page_source):
    soup = BeautifulSoup(page_source, "html.parser")
    # getting general stats table
    general_stats = []
    general_stats_table = soup.find("table", attrs={"id": "tblGeneralStats"})
    table_body = general_stats_table.find("tbody")
    rows = table_body.find_all("tr")
    for row in rows:
        cols = row.find_all("td")
        cols = [ele.text.strip() for ele in cols]
        general_stats.append([ele for ele in cols if ele])  # Get rid of empty values

    general_stats = general_stats[:4]
    res = ""
    for row in general_stats:
        # formating the number (123456 -> 123 456)
        num = f"{int(row[1]):,}"
        num = num.replace(",", " ")
        res += "**" + row[0] + "** " + num + "\n"
    res += "*" + scrape_last_updated(page_source) + "*"
    return res


def scrape_last_updated(page_source):
    soup = BeautifulSoup(page_source, "html.parser")
    result = soup.find(id="lastUpdated")
    return result.text


def scrape_alltime_leaderboard(page_source):
    soup = BeautifulSoup(page_source, "html.parser")
    # getting general stats table
    at_leaderboard = []
    at_leaderboard_table = soup.find("table", attrs={"id": "tblToplistAlltime"})
    table_body = at_leaderboard_table.find("tbody")
    rows = table_body.find_all("tr")
    for row in rows:
        cols = row.find_all("td")
        cols = [ele.text.strip() for ele in cols]
        at_leaderboard.append(
            [ele.replace("\u202f", "") for ele in cols if ele]
        )  # Get rid of empty values

    return at_leaderboard


def scrape_canvas_leaderboard(page_source):
    soup = BeautifulSoup(page_source, "html.parser")
    # getting general stats table
    c_leaderboard = []
    c_leaderboard_table = soup.find("table", attrs={"id": "tblToplistCurrent"})
    table_body = c_leaderboard_table.find("tbody")
    rows = table_body.find_all("tr")
    for row in rows:
        cols = row.find_all("td")
        cols = [ele.text.strip() for ele in cols]
        c_leaderboard.append(
            [ele.replace("\u202f", "") for ele in cols if ele]
        )  # Get rid of empty values

    return c_leaderboard


def get_stats(user, at_table):
    for u in at_table:
        if u[1] == user:
            return int(u[2])
    return -1


if __name__ == "__main__":
    driver = init_driver()
    page_source = get_page_source(driver)
    # print(scrape_general_stats(page_source))
    # print(scrape_last_updated(page_source))
    at_table = scrape_canvas_leaderboard(page_source)
    print(get_stats("GrayTurtles", at_table))
