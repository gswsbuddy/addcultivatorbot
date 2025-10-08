import os
import sys
import time
import traceback
import pandas as pd
import requests
import io
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

# 🔐 Load license keys from Google Sheet
def load_license_map_from_sheet():
    try:
        sheet_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQHrRtsmcHr36eDKUk7JNofQ1LGOmVyFq7rHpj3vMUaKxw2BF8sNY-tuoI9xLNi4e1cfP85El50_YSd/pub?output=csv"
        response = requests.get(sheet_url)
        df_keys = pd.read_csv(io.StringIO(response.text))
        df_keys.dropna(subset=["VILLAGECODE", "LICENSEKEY"], inplace=True)
        return dict(zip(df_keys["VILLAGECODE"].astype(str), df_keys["LICENSEKEY"].astype(str)))
    except Exception as e:
        print(f"❌ Failed to load license map: {e}")
        return {}

# 🛡️ Safe input with JS fallback
def safe_input(driver, element_id, value):
    try:
        field = driver.find_element(By.ID, element_id)
        if field.is_enabled() and field.get_attribute("readonly") != "true":
            field.clear()
            field.send_keys(value)
        else:
            raise Exception("Field not editable")
    except:
        driver.execute_script(f"document.getElementById('{element_id}').value = '{value}'")

# 🔄 Update a single survey row
def update_survey_row(driver, i, khata, khata_mobile_map, log_output):
    log_output.append(f"🧪 Entering update_survey_row for Row {i} in Khata {khata}")
    try:
        WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, f"anubhavadarExtent{i}")))
        driver.execute_script("arguments[0].scrollIntoView(true);", driver.find_element(By.ID, f"anubhavadarExtent{i}"))
    except Exception as e:
        log_output.append(f"❌ Row {i}: anubhavadarExtent{i} not found — skipping. Error: {e}")
        return False

    try:
        available_raw = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.ID, f"availableExtent{i}"))
        ).get_attribute("value")
        available = float(available_raw)
        log_output.append(f"🔍 Row {i}: Available extent = {available}")
    except Exception as e:
        log_output.append(f"❌ Row {i}: Failed to read available extent: {e}")
        return False

    if available == 0.0:
        log_output.append(f"⏭️ Row {i}: Skipped (available extent is 0.0)")
        return False

    try:
        extent_raw = driver.find_element(By.ID, f"anubhavadarExtent{i}").get_attribute("value")
        extent = float(extent_raw)
        log_output.append(f"🔍 Row {i}: Anubhavadar extent = {extent}")
    except Exception as e:
        log_output.append(f"❌ Row {i}: Failed to read anubhavadar extent: {e}")
        return False

    if extent <= 0.0:
        log_output.append(f"⏭️ Row {i}: Extent is zero, skipping Owner flow")
        return False

    try:
        mobile_field = driver.find_element(By.ID, f"mobile{i}")
        current_mobile = mobile_field.get_attribute("value").strip()

        if current_mobile in ["", "0", "0000000000"] or len(current_mobile) != 10:
            new_mobile = khata_mobile_map.get(khata, "")
            if new_mobile and len(new_mobile) == 10 and new_mobile.isdigit() and new_mobile[0] in "6789":
                mobile_field.clear()
                mobile_field.send_keys(new_mobile)
                log_output.append(f"📱 Row {i}: Mobile replaced with {new_mobile}")
                with open("mobile_replacements.txt", "a") as log:
                    log.write(f"{khata}, Row {i}, Replaced with: {new_mobile}\n")
            else:
                log_output.append(f"❌ Row {i}: Invalid mobile in Excel for Khata {khata}, skipping Owner Update")
                with open("invalid_mobile_log.txt", "a") as log:
                    log.write(f"{khata}, Row {i} - Invalid mobile: {new_mobile}\n")
                return False
        else:
            log_output.append(f"✅ Row {i}: Mobile already present ({current_mobile})")

        Select(driver.find_element(By.ID, f"searchParam{i}")).select_by_value("1")
        driver.execute_script(f"onUserTypeChange({i}, '1')")
        log_output.append(f"✅ Row {i}: Owner selected")

        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "occupantExtentOE")))
        driver.find_element(By.ID, "occupantExtentOE").clear()
        driver.find_element(By.ID, "occupantExtentOE").send_keys(str(extent))

        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "ownerbtnId")))
        driver.find_element(By.ID, "ownerbtnId").click()
        log_output.append("💾 Owner Update submitted.")

        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CLASS_NAME, "swal2-confirm"))).click()
        log_output.append("✅ Final confirmation clicked.")

        time.sleep(1.5)
        return True

    except Exception as e:
        log_output.append(f"❌ Row {i} error: {e}")
        return False
def update_all_rows(driver, khata, khata_mobile_map, log_output):
    i = 0
    updated_rows = 0
    while True:
        try:
            WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.ID, f"anubhavadarExtent{i}")))
            driver.execute_script("arguments[0].scrollIntoView(true);", driver.find_element(By.ID, f"anubhavadarExtent{i}"))
            modal_triggered = update_survey_row(driver, i, khata, khata_mobile_map, log_output)
            if modal_triggered:
                updated_rows += 1
                log_output.append(f"🔁 Modal triggered on row {i}, restarting row scan...")
                i = 0
                continue
            i += 1
        except:
            log_output.append(f"🔚 Finished updating rows for Khata {khata}")
            break

    if updated_rows == 0:
        log_output.append(f"⚠️ Khata {khata} had no eligible rows for update.")
        with open("skipped_khatas.txt", "a") as log:
            log.write(f"{khata} - No eligible rows\n")
    else:
        log_output.append(f"📊 Khata {khata}: {updated_rows} rows updated.")
    return updated_rows


def run_ecrop_bot(df, username, password, log_output, village_code):
    try:
        base_path = sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.dirname(__file__)
        driver_path = os.path.join(os.path.dirname(__file__), "chromedriver.exe")
        service = Service(driver_path)

        options = Options()
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")

        driver = webdriver.Chrome(service=service, options=options)

    except Exception as e:
        log_output.append(f"❌ Failed to launch ChromeDriver: {e}")
        return

    if "KNO" not in df.columns or "Mobile" not in df.columns:
        log_output.append("❌ Excel missing required columns: 'KNO' and/or 'Mobile'")
        driver.quit()
        return

    khata_list = df["KNO"].dropna().astype(str).tolist()
    khata_mobile_map = dict(zip(df["KNO"].astype(str), df["Mobile"].astype(str)))

    try:
        driver.get("https://karshak.ap.gov.in/ecrop/")
        time.sleep(10)

        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.NAME, "username")))
        driver.find_element(By.NAME, "username").send_keys(username)
        driver.find_element(By.ID, "password").send_keys(password)

        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "transactionDropdown")))
        driver.find_element(By.ID, "transactionDropdown").click()
        driver.find_element(By.LINK_TEXT, "Add/Update Cultivator").click()

        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "village")))
        Select(driver.find_element(By.ID, "village")).select_by_value(str(village_code))
        log_output.append(f"✅ Village selected: {village_code}")

        time.sleep(5)

        log_output.append("✅ Navigation complete. Village selected.")

        for khata in khata_list:
            log_output.append(f"\n🚜 Starting Khata: {khata}")
            try:
                WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, "fromKhnoId")))
                khata_input = driver.find_element(By.ID, "fromKhnoId")
                khata_input.clear()
                khata_input.send_keys(khata)
                WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "searchId")))
                driver.find_element(By.ID, "searchId").click()
                log_output.append(f"✅ Khata {khata} entered and searched.")
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, "//*[starts-with(@id,'anubhavadarExtent')]"))
                    )
                    log_output.append("✅ Survey rows detected after search")
                except Exception as e:
                    log_output.append(f"⚠️ No survey rows visible after search: {e}")

            except Exception as e:
                log_output.append(f"❌ Error entering Khata {khata}: {e}")
                continue

            update_all_rows(driver, khata, khata_mobile_map, log_output)

        log_output.append("✅ All Khatas processed.")

    except Exception as e:
        log_output.append(f"❌ Fatal error during navigation or update: {e}")
        try:
            screenshot_path = os.path.join(os.getcwd(), "fatal_error.png")
            driver.save_screenshot(screenshot_path)
            log_output.append(f"📸 Screenshot saved: {screenshot_path}")
        except:
            log_output.append("⚠️ Failed to save screenshot.")

    finally:
        driver.quit()
        log_output.append("🛑 Browser closed.")
