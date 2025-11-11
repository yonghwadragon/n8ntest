# blog_selenium_server.py
# FastAPI 로 JSON(title, body)을 받아 네이버 블로그에 자동 게시

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
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ─────────────────────────────
# 환경 설정
# ─────────────────────────────
load_dotenv()  # NAVER_ID, NAVER_PW 등 .env 로드

NAV_ID = os.getenv("NAVER_ID")
NAV_PW = os.getenv("NAVER_PW")
BLOG_WRITE_URL = "https://blog.naver.com/GoBlogWrite.naver"
MODEL_WAIT = 15  # WebDriverWait 기본값

# ─────────────────────────────
# FastAPI 앱
# ─────────────────────────────
app = FastAPI()


# ─────────────────────────────
# 드라이버 초기화
# ─────────────────────────────
def init_driver() -> webdriver.Chrome:
    """ChromeDriver 초기화(브라우저 자동 종료 방지)"""
    opts = Options()
    opts.add_experimental_option("detach", True)
    # Chrome 콘솔-스팸(DevTools, GCM 등) 숨기기
    opts.add_experimental_option(
        "excludeSwitches", ["enable-logging", "enable-automation"]
    )
    opts.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=opts,
    )
    # 브라우저 크기 고정
    driver.set_window_size(1600, 950)
    return driver


driver: webdriver.Chrome = init_driver()
wait: WebDriverWait | None = None  # 로그인 후에 할당


# ─────────────────────────────
# 네이버 로그인
# ─────────────────────────────
def naver_login(driver: webdriver.Chrome) -> WebDriverWait:
    """네이버 로그인 후 WebDriverWait 반환"""
    driver.get("https://nid.naver.com/nidlogin.login")
    time.sleep(0.5)  # 페이지 로딩 대기시간

    driver.find_element(By.ID, "id").click()
    pyperclip.copy(NAV_ID)
    driver.find_element(By.ID, "id").send_keys(Keys.CONTROL, "v")
    time.sleep(0.1)

    driver.find_element(By.ID, "pw").click()
    pyperclip.copy(NAV_PW)
    driver.find_element(By.ID, "pw").send_keys(Keys.CONTROL, "v")
    pyperclip.copy("")  # 클립보드 비우기
    time.sleep(0.1)

    driver.find_element(By.ID, "log.login").click()
    time.sleep(0.5)  # 로그인 완료 대기시간
    return WebDriverWait(driver, MODEL_WAIT)


# 서버 시작될 때 한 번만 로그인
wait = naver_login(driver)


# ─────────────────────────────
# 블로그 글쓰기 페이지
# ─────────────────────────────
def open_write_page(driver: webdriver.Chrome, wait: WebDriverWait):
    """블로그 글쓰기 페이지 접속 및 iframe 진입, 팝업/도움말 닫기"""
    driver.get(BLOG_WRITE_URL)

    # 메인 프레임 전환
    wait.until(
        EC.frame_to_be_available_and_switch_to_it(
            (By.CSS_SELECTOR, "iframe#mainFrame")
        )
    )

    # 이어쓰기 팝업 취소
    try:
        cancel_btn = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, ".se-popup-button-cancel")
            )
        )
        cancel_btn.click()
        wait.until(
            EC.invisibility_of_element_located(
                (By.CSS_SELECTOR, ".se-popup-dim")
            )
        )
    except TimeoutException:
        pass

    # 도움말 패널 닫기(존재할 때까지 반복)
    while True:
        try:
            driver.find_element(
                By.CSS_SELECTOR, ".se-help-panel-close-button"
            ).click()
            time.sleep(0.05)  # 루프 속도
        except WebDriverException:
            break


# ─────────────────────────────
# v1 코드 그대로: 글쓰기 함수
# ─────────────────────────────
def write_post(
    driver: webdriver.Chrome,
    wait: WebDriverWait,
    title: str,
    body: str,
):
    """제목과 본문 입력 후 저장"""
    actions = ActionChains(driver)

    # ActionChains: 입력 전 포커스, 마우스 이동 보장
    title_area = wait.until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, ".se-section-documentTitle")
        )
    )
    actions.move_to_element(title_area).click().perform()
    for ch in title:
        actions.send_keys(ch).pause(0.0001)
    actions.perform()
    actions.reset_actions()

    # 본문
    body_area = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-section-text"))
    )
    actions.move_to_element(body_area).click().perform()
    for line in body.splitlines():
        for ch in line:
            actions.send_keys(ch).pause(0.0001)
        actions.send_keys(Keys.ENTER).pause(0.0001)
    actions.perform()

    # 저장
    save_btn = wait.until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, ".save_btn__bzc5B")
        )
    )
    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'});", save_btn
    )
    time.sleep(0.05)  # 스크롤 안정화 시간
    try:
        save_btn.click()
    except ElementClickInterceptedException:
        driver.execute_script("arguments[0].click();", save_btn)
    # ‘저장됨’ 토스트 or URL 변화 대기 (최대 7초)
    try:
        wait.until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    ".toast_item__success, .se-toast-item__success",
                )
            )
        )
    except TimeoutException:
        pass  # 토스트가 안 보여도 이어서 진행
    time.sleep(0.2)  # 저장 대기시간


# ─────────────────────────────
# FastAPI용 입력 모델
# ─────────────────────────────
class PostRequest(BaseModel):
    title: str
    body: str


# ─────────────────────────────
# 헬스체크 엔드포인트 (선택)
# ─────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}


# ─────────────────────────────
# 실제 포스팅 엔드포인트
# ─────────────────────────────
@app.post("/post-to-naver")
async def post_to_naver(req: PostRequest):
    """
    JSON { "title": "...", "body": "..." } 를 받아
    기존 v1 로직을 그대로 사용해 네이버 블로그에 글 작성
    """
    try:
        # 제목이 비어 있을 경우, 본문 첫 줄 또는 첫 문장으로 자동 생성
        title = req.title.strip() if req.title.strip() else req.body.strip().split("\n")[0][:40]
        
        open_write_page(driver, wait)
        write_post(driver, wait, title, req.body)
        return {"status": "success", "title": title}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))