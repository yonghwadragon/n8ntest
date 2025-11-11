# blog_selenium_server.py
# FastAPI 로 JSON(title, body)을 받아 네이버 블로그에 자동 게시 (Render 호환 완성 버전)

import os
import time
import pyperclip
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import chromedriver_autoinstaller  # ✅ 자동 설치용 추가


# ─────────────────────────────
# 환경 설정
# ─────────────────────────────
load_dotenv()
NAV_ID = os.getenv("NAVER_ID")
NAV_PW = os.getenv("NAVER_PW")
BLOG_WRITE_URL = "https://blog.naver.com/GoBlogWrite.naver"
MODEL_WAIT = 15

app = FastAPI()


# ─────────────────────────────
# Chrome 드라이버 초기화 (Render 호환)
# ─────────────────────────────
def init_driver() -> webdriver.Chrome:
    """Render 환경에서도 작동 가능한 ChromeDriver 초기화"""
    chromedriver_autoinstaller.install()

    opts = Options()
    opts.add_argument("--headless=new")  # GUI 없이 실행
    opts.add_argument("--no-sandbox")  # Render 필수 옵션
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920x1080")
    opts.add_argument("--disable-infobars")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--remote-debugging-port=9222")
    opts.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    # ✅ Render용 Chrome 실행 경로 자동 감지
    for path in ["/usr/bin/chromium-browser", "/usr/bin/chromium", "/usr/bin/google-chrome"]:
        if os.path.exists(path):
            opts.binary_location = path
            break

    driver = webdriver.Chrome(options=opts)
    driver.set_window_size(1600, 950)
    return driver


driver: webdriver.Chrome = init_driver()
wait: WebDriverWait | None = None


# ─────────────────────────────
# 네이버 로그인
# ─────────────────────────────
def naver_login(driver: webdriver.Chrome) -> WebDriverWait:
    """네이버 로그인"""
    driver.get("https://nid.naver.com/nidlogin.login")
    time.sleep(1)

    driver.find_element(By.ID, "id").click()
    pyperclip.copy(NAV_ID)
    driver.find_element(By.ID, "id").send_keys(Keys.CONTROL, "v")
    time.sleep(0.1)

    driver.find_element(By.ID, "pw").click()
    pyperclip.copy(NAV_PW)
    driver.find_element(By.ID, "pw").send_keys(Keys.CONTROL, "v")
    pyperclip.copy("")
    time.sleep(0.1)

    driver.find_element(By.ID, "log.login").click()
    time.sleep(1)
    return WebDriverWait(driver, MODEL_WAIT)


# 서버 시작 시 로그인 시도
try:
    wait = naver_login(driver)
except Exception as e:
    print("⚠️ 로그인 실패:", e)


# ─────────────────────────────
# 블로그 글쓰기 페이지
# ─────────────────────────────
def open_write_page(driver: webdriver.Chrome, wait: WebDriverWait):
    """블로그 글쓰기 페이지 열기"""
    driver.get(BLOG_WRITE_URL)

    wait.until(EC.frame_to_be_available_and_switch_to_it((By.CSS_SELECTOR, "iframe#mainFrame")))

    try:
        cancel_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-popup-button-cancel")))
        cancel_btn.click()
        wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, ".se-popup-dim")))
    except TimeoutException:
        pass


# ─────────────────────────────
# 글쓰기 함수
# ─────────────────────────────
def write_post(driver: webdriver.Chrome, wait: WebDriverWait, title: str, body: str):
    """제목과 본문 작성"""
    actions = ActionChains(driver)

    title_area = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-section-documentTitle")))
    actions.move_to_element(title_area).click().perform()
    for ch in title:
        actions.send_keys(ch).pause(0.0001)
    actions.perform()
    actions.reset_actions()

    body_area = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-section-text")))
    actions.move_to_element(body_area).click().perform()
    for line in body.splitlines():
        for ch in line:
            actions.send_keys(ch).pause(0.0001)
        actions.send_keys(Keys.ENTER).pause(0.0001)
    actions.perform()


# ─────────────────────────────
# 데이터 모델
# ─────────────────────────────
class PostRequest(BaseModel):
    title: str
    body: str


# ─────────────────────────────
# 헬스 체크
# ─────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}


# ─────────────────────────────
# 포스팅 엔드포인트
# ─────────────────────────────
@app.post("/post-to-naver")
async def post_to_naver(req: PostRequest):
    try:
        title = req.title.strip() if req.title.strip() else req.body.strip().split("\n")[0][:40]
        open_write_page(driver, wait)
        write_post(driver, wait, title, req.body)
        return {"status": "success", "title": title}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
