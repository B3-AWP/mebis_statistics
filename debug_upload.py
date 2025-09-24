import os
import configparser
import json
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

def load_config():
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config

def debug_upload():
    """Debug upload functionality with detailed output"""

    # Load config
    config = load_config()
    username = config['login']['username']
    password = config['login']['password']

    # Test data
    test_data = {"test": "debug upload", "timestamp": datetime.now().isoformat()}
    filename = f"debug_upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    print("=" * 60)
    print("DEBUG UPLOAD TEST")
    print("=" * 60)

    # Create temp file
    temp_dir = "./temp"
    os.makedirs(temp_dir, exist_ok=True)
    temp_file_path = os.path.join(temp_dir, filename)

    with open(temp_file_path, 'w', encoding='utf-8') as f:
        json.dump(test_data, f, ensure_ascii=False)

    abs_file_path = os.path.abspath(temp_file_path)
    print(f"DEBUG: Test-Datei: {abs_file_path}")
    print(f"DEBUG: Größe: {os.path.getsize(abs_file_path)} bytes")

    # Browser setup
    options = Options()
    options.add_argument('--window-size=1400,900')
    driver = webdriver.Chrome(options=options)

    try:
        # Login
        print("DEBUG: Login...")
        driver.get("https://6072.drive.bycs.de/")
        time.sleep(3)

        username_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#input-username"))
        )
        username_field.send_keys(username)

        password_field = driver.find_element(By.CSS_SELECTOR, "input[name='password']")
        password_field.send_keys(password)

        login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        login_button.click()

        time.sleep(5)
        print(f"DEBUG: Nach Login URL: {driver.current_url}")

        # Navigate to folder
        target_url = "https://6072.drive.bycs.de/files/spaces/project/aeup12/Segel_Export"
        driver.get(target_url)
        time.sleep(5)

        print(f"DEBUG: Im Ordner URL: {driver.current_url}")
        print(f"DEBUG: Seitentitel: {driver.title}")

        # Detailed element analysis
        print("\n" + "="*40)
        print("ALLE INPUT ELEMENTE:")
        print("="*40)

        all_inputs = driver.find_elements(By.TAG_NAME, "input")
        for i, inp in enumerate(all_inputs):
            try:
                inp_type = inp.get_attribute("type") or "None"
                inp_id = inp.get_attribute("id") or "None"
                inp_class = inp.get_attribute("class") or "None"
                inp_name = inp.get_attribute("name") or "None"
                inp_accept = inp.get_attribute("accept") or "None"
                visible = inp.is_displayed()
                print(f"Input {i:2d}: type={inp_type:10} id={inp_id[:15]:15} class={inp_class[:20]:20} name={inp_name[:15]:15} accept={inp_accept[:10]:10} visible={visible}")
            except Exception as e:
                print(f"Input {i}: Error reading attributes: {e}")

        print("\n" + "="*40)
        print("ALLE BUTTON ELEMENTE:")
        print("="*40)

        all_buttons = driver.find_elements(By.TAG_NAME, "button")
        for i, btn in enumerate(all_buttons):
            try:
                btn_text = (btn.text or "").strip()[:30]
                btn_id = btn.get_attribute("id") or ""
                btn_class = (btn.get_attribute("class") or "")[:30]
                btn_title = btn.get_attribute("title") or ""
                btn_aria_label = btn.get_attribute("aria-label") or ""
                visible = btn.is_displayed()
                print(f"Button {i:2d}: text='{btn_text}' id='{btn_id[:15]}' class='{btn_class}' title='{btn_title[:20]}' aria='{btn_aria_label[:20]}' visible={visible}")
            except Exception as e:
                print(f"Button {i}: Error: {e}")

        print("\n" + "="*40)
        print("SUCHE NACH UPLOAD ELEMENTEN:")
        print("="*40)

        # Test specific selectors
        upload_selectors = [
            "input[type='file']",
            "input[accept]",
            "[data-testid*='upload']",
            "[data-upload]",
            ".upload-input",
            "#upload-input",
            "input.file-input",
            "input[multiple]"
        ]

        found_inputs = []
        for selector in upload_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    print(f"OK Gefunden '{selector}': {len(elements)} Element(e)")
                    for j, elem in enumerate(elements):
                        visible = elem.is_displayed()
                        elem_id = elem.get_attribute("id") or ""
                        elem_class = elem.get_attribute("class") or ""
                        print(f"   Element {j}: visible={visible} id='{elem_id}' class='{elem_class[:30]}'")
                        if elem not in found_inputs:
                            found_inputs.append((elem, selector))
                else:
                    print(f"NO Nicht gefunden: '{selector}'")
            except Exception as e:
                print(f"ERROR Fehler bei '{selector}': {e}")

        print(f"\nGESAMT GEFUNDENE UPLOAD INPUTS: {len(found_inputs)}")

        # Try to upload with found inputs
        upload_success = False
        for i, (inp, selector) in enumerate(found_inputs):
            try:
                print(f"\nTESTE UPLOAD mit Input {i} ({selector}):")

                # Scroll to element
                driver.execute_script("arguments[0].scrollIntoView();", inp)
                time.sleep(1)

                print(f"  - Element in view gebracht")

                # Try to interact
                inp.send_keys(abs_file_path)
                print(f"  - Dateipfad gesendet: {abs_file_path}")

                time.sleep(3)
                print("  - Warte 3 Sekunden...")

                # Check for upload progress/completion
                progress_indicators = driver.find_elements(By.CSS_SELECTOR, ".upload-progress, .progress, .uploading, [class*='progress'], [class*='upload']")
                if progress_indicators:
                    print(f"  - Upload-Progress gefunden: {len(progress_indicators)} Elemente")
                    time.sleep(5)
                else:
                    print("  - Kein Upload-Progress sichtbar")

                # Check if file appears
                time.sleep(2)
                file_check_selectors = [
                    f"[title*='{filename}']",
                    f"[data-filename*='{filename}']",
                    f"td:contains('{filename}')",
                    f"div:contains('{filename}')",
                    f"span:contains('{filename}')",
                    f"a[href*='{filename}']"
                ]

                file_found = False
                for check_sel in file_check_selectors:
                    try:
                        file_elements = driver.find_elements(By.CSS_SELECTOR, check_sel)
                        for elem in file_elements:
                            elem_text = elem.text or elem.get_attribute("title") or elem.get_attribute("data-filename") or ""
                            if filename in elem_text:
                                print(f"  ✓ DATEI GEFUNDEN mit '{check_sel}': '{elem_text}'")
                                file_found = True
                                upload_success = True
                                break
                    except:
                        pass

                if file_found:
                    break
                else:
                    print("  ✗ Datei noch nicht sichtbar")

            except Exception as e:
                print(f"  ✗ Fehler beim Upload-Test mit Input {i}: {e}")

        print("\n" + "="*60)
        if upload_success:
            print("SUCCESS: UPLOAD ERFOLGREICH!")
        else:
            print("FAILED: UPLOAD FEHLGESCHLAGEN")
            print("\nBrowser bleibt offen für manuelle Inspektion...")
            print("Versuchen Sie manuell einen Upload und beobachten Sie die Elemente.")
            input("Drücken Sie Enter, um fortzufahren...")
        print("="*60)

    finally:
        try:
            driver.quit()
        except:
            pass

        try:
            os.remove(abs_file_path)
        except:
            pass

if __name__ == "__main__":
    debug_upload()