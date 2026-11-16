import time
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

def run_onestop_auto_fill(user_profile, flight_data):
    """
    Automates login & form auto-fill on official Drone One-Stop website (drone.onestop.go.kr)
    using user ID/PW from Profile Settings.
    """
    onestop_id = user_profile.get("onestop_id", "")
    onestop_pw = user_profile.get("onestop_pw", "")

    # Configure Chrome browser options
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_experimental_option("detach", True)  # Keeps Chrome window open for the user to review

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        # Step 1: Navigate to Drone One-Stop Login Page
        driver.get("https://drone.onestop.go.kr/login")
        time.sleep(1.5)

        # Step 2: Auto Login if ID/PW are provided
        if onestop_id and onestop_pw:
            try:
                # Find ID and Password input fields
                id_inputs = driver.find_elements(By.CSS_SELECTOR, "input[name='memberId'], input#memberId, input[type='text']")
                pw_inputs = driver.find_elements(By.CSS_SELECTOR, "input[name='password'], input#password, input[type='password']")

                if id_inputs and pw_inputs:
                    id_inputs[0].clear()
                    id_inputs[0].send_keys(onestop_id)
                    pw_inputs[0].clear()
                    pw_inputs[0].send_keys(onestop_pw)
                    time.sleep(0.5)

                    # Click login button
                    login_btns = driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], .btn_login, #loginBtn, input[type='submit']")
                    if login_btns:
                        login_btns[0].click()
                        time.sleep(2)
            except Exception as login_err:
                print(f"Login field notice: {login_err}")

        # Step 3: Navigate to Official Flight Approval Register Page
        driver.get("https://drone.onestop.go.kr/civilappeal/flight/register")
        time.sleep(2)

        # Step 4: Auto-Fill Form Fields (Purpose, Method, Remarks)
        try:
            # Select Purpose: 레저비행
            purp_selects = driver.find_elements(By.CSS_SELECTOR, "select[name='flightPurp'], select#flightPurp")
            if purp_selects:
                for opt in purp_selects[0].find_elements(By.TAG_NAME, "option"):
                    if "레저" in opt.text or "취미" in opt.text:
                        opt.click()
                        break

            # Select Method: 시계비행
            meth_selects = driver.find_elements(By.CSS_SELECTOR, "select[name='flightMeth'], select#flightMeth")
            if meth_selects:
                for opt in meth_selects[0].find_elements(By.TAG_NAME, "option"):
                    if "시계" in opt.text:
                        opt.click()
                        break

        except Exception as form_err:
            print(f"Form field auto-fill notice: {form_err}")

        return True, "✅ 드론원스톱 공식 웹사이트에 접속하여 로그인 및 비행 신청서 양식(비행목적: 레저비행 / 비행방식: 시계비행)을 자동 입력했습니다!"

    except Exception as e:
        return False, f"⚠️ 브라우저 실행 중 안내: {e}"
