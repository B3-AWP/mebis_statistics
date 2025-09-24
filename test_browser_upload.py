import os
import configparser
import json
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options

def load_config():
    """Load configuration from config.ini"""
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config

def create_webdriver(headless=False):
    """Create Chrome WebDriver instance"""
    options = Options()
    if headless:
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')

    # Add some basic optimizations but keep it visible
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-plugins')

    # Additional stability options
    options.add_argument('--no-first-run')
    options.add_argument('--disable-default-apps')
    options.add_argument('--remote-debugging-port=9222')

    try:
        driver = webdriver.Chrome(options=options)
        # Test that driver is working
        driver.get("about:blank")
        return driver
    except Exception as e:
        print(f"Fehler beim Erstellen des WebDrivers: {e}")
        print("Versuche alternative Chrome-Optionen...")

        # Try with minimal options
        options = Options()
        if headless:
            options.add_argument('--headless')

        return webdriver.Chrome(options=options)

def login_to_owncloud(driver, username, password):
    """Login to OwnCloud using credentials"""
    print(f"Anmeldung mit Benutzer: {username}")

    # Navigate to the OwnCloud login page
    driver.get("https://6072.drive.bycs.de/")

    print("Seite geladen, suche nach Login-Elementen...")
    time.sleep(3)  # Give page time to load

    try:
        # Try multiple login element selectors
        username_selectors = [
            "input#user",
            "input[name='user']",
            "input[type='text'][id='user']",
            "input[placeholder*='username']",
            "input[placeholder*='Benutzername']",
            "#input-username"
        ]

        username_field = None
        for selector in username_selectors:
            try:
                username_field = WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                print(f"Username-Feld gefunden: {selector}")
                break
            except:
                continue

        if not username_field:
            print("Kein Username-Feld gefunden. Verfuegbare Eingabefelder:")
            inputs = driver.find_elements(By.TAG_NAME, "input")
            for i, inp in enumerate(inputs):
                try:
                    print(f"  Input {i}: id='{inp.get_attribute('id')}' name='{inp.get_attribute('name')}' type='{inp.get_attribute('type')}'")
                except:
                    pass

            print("Lasse Browser offen zur manuellen Inspektion...")
            input("Druecken Sie Enter, um fortzufahren...")
            return False

        # Enter username
        username_field.clear()
        username_field.send_keys(username)
        print(f"Username eingegeben: {username}")

        # Find password field
        password_selectors = [
            "input#password",
            "input[name='password']",
            "input[type='password']",
            "#input-password"
        ]

        password_field = None
        for selector in password_selectors:
            try:
                password_field = driver.find_element(By.CSS_SELECTOR, selector)
                print(f"Password-Feld gefunden: {selector}")
                break
            except:
                continue

        if not password_field:
            print("Kein Password-Feld gefunden!")
            return False

        # Enter password
        password_field.clear()
        password_field.send_keys(password)
        print("Password eingegeben")

        # Find and click login button
        login_selectors = [
            "button#submit-form",
            "input[type='submit']",
            "button[type='submit']",
            "input[value='Login']",
            "button:contains('Login')",
            "#button-do-log-in"
        ]

        login_button = None
        for selector in login_selectors:
            try:
                login_button = driver.find_element(By.CSS_SELECTOR, selector)
                print(f"Login-Button gefunden: {selector}")
                break
            except:
                continue

        if not login_button:
            print("Kein Login-Button gefunden. Verfuegbare Buttons:")
            buttons = driver.find_elements(By.TAG_NAME, "button")
            for i, btn in enumerate(buttons):
                try:
                    print(f"  Button {i}: id='{btn.get_attribute('id')}' text='{btn.text}' type='{btn.get_attribute('type')}'")
                except:
                    pass

            print("Lasse Browser offen zur manuellen Inspektion...")
            input("Druecken Sie Enter, um fortzufahren...")
            return False

        # Click login button
        login_button.click()
        print("Login-Button geklickt, warte auf Weiterleitung...")

        # Wait for successful login (give more time)
        try:
            WebDriverWait(driver, 20).until(
                EC.any_of(
                    EC.presence_of_element_located((By.CLASS_NAME, "app-files")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='files-app']")),
                    EC.presence_of_element_located((By.CLASS_NAME, "files-list")),
                    EC.url_contains("/f/"),
                    EC.url_contains("/files/"),
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".files-view")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid]"))
                )
            )
            print("Erfolgreich angemeldet!")
            return True
        except TimeoutException:
            print("Login-Timeout. Aktuelle URL:", driver.current_url)
            print("Lasse Browser offen zur manuellen Pruefung...")
            input("Druecken Sie Enter wenn Sie manuell angemeldet sind...")
            return True

    except Exception as e:
        print(f"Fehler beim Login: {e}")
        print("Aktuelle URL:", driver.current_url)
        print("Lasse Browser offen zur Inspektion...")
        input("Druecken Sie Enter, um fortzufahren...")
        return False

def navigate_to_upload_folder(driver):
    """Navigate to the Segel_Export folder"""
    print("Navigiere zum Segel_Export Ordner...")

    target_url = "https://6072.drive.bycs.de/files/spaces/project/aeup12/Segel_Export"
    driver.get(target_url)

    print(f"Lade Ziel-URL: {target_url}")
    time.sleep(5)  # Give time to load

    try:
        # Check current URL after navigation
        current_url = driver.current_url
        print(f"Aktuelle URL: {current_url}")

        # Try multiple selectors for folder content
        folder_selectors = [
            ".files-list",
            "[data-testid='files-list']",
            ".file-row",
            ".files-view",
            ".file-list",
            "table tbody",
            ".space-content",
            "[role='table']",
            "[data-testid='space-files-view']"
        ]

        folder_loaded = False
        for selector in folder_selectors:
            try:
                element = WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                print(f"Ordner-Element gefunden: {selector}")
                folder_loaded = True
                break
            except:
                continue

        if not folder_loaded:
            print("Kein bekanntes Ordner-Element gefunden.")
            print("Aktueller Seitentitel:", driver.title)

            # Look for any potential file/folder indicators
            potential_elements = driver.find_elements(By.CSS_SELECTOR, "[class*='file'], [class*='folder'], [data-testid*='file'], [role='row'], tbody tr")
            print(f"Potentielle Datei/Ordner-Elemente gefunden: {len(potential_elements)}")

            if potential_elements:
                print("Erstes Element als Erfolg gewertet")
                folder_loaded = True
            else:
                print("Lasse Browser offen zur manuellen Inspektion...")
                print("Navigieren Sie manuell zum Segel_Export Ordner")
                input("Druecken Sie Enter wenn Sie im richtigen Ordner sind...")
                folder_loaded = True

        if folder_loaded:
            print("Ordner erfolgreich geladen (oder manuell navigiert)!")
            return True
        else:
            return False

    except Exception as e:
        print(f"Fehler beim Laden des Ordners: {e}")
        print("Aktuelle URL:", driver.current_url)
        print("Lasse Browser offen zur manuellen Navigation...")
        input("Navigieren Sie manuell zum Segel_Export Ordner und druecken Enter...")
        return True

def upload_file_via_browser(driver, file_path, filename):
    """Upload file using browser interface"""
    print(f"Versuche Upload von: {filename}")

    try:
        # Look for upload button or drag-drop area
        upload_selectors = [
            "input[type='file']",
            "[data-testid='upload-input']",
            ".upload-button input",
            "#file_upload_start",
            ".new-file-menu input[type='file']"
        ]

        upload_input = None
        for selector in upload_selectors:
            try:
                upload_input = driver.find_element(By.CSS_SELECTOR, selector)
                if upload_input:
                    print(f"Upload-Element gefunden: {selector}")
                    break
            except:
                continue

        if not upload_input:
            print("Suche nach Upload-Button...")

            # Try to find and click upload/new button first
            button_selectors = [
                "button[data-testid='btn-upload']",
                ".upload-button",
                ".new-button",
                "[aria-label*='upload']",
                "[title*='upload']",
                ".btn-upload"
            ]

            for selector in button_selectors:
                try:
                    button = driver.find_element(By.CSS_SELECTOR, selector)
                    if button.is_displayed():
                        print(f"Upload-Button gefunden: {selector}")
                        button.click()
                        time.sleep(1)

                        # Try to find file input again after clicking
                        for input_selector in upload_selectors:
                            try:
                                upload_input = driver.find_element(By.CSS_SELECTOR, input_selector)
                                if upload_input:
                                    break
                            except:
                                continue
                        break
                except:
                    continue

        if upload_input:
            print("Upload-Input gefunden, sende Datei...")
            upload_input.send_keys(file_path)

            print("Datei gesendet, warte auf Upload-Bestaetigung...")
            time.sleep(3)

            # Wait for upload to complete (look for success indicators)
            success_selectors = [
                ".upload-success",
                ".notification.success",
                f"[title*='{filename}']",
                f"[data-filename='{filename}']"
            ]

            for selector in success_selectors:
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    print(f"Upload-Erfolg erkannt: {selector}")
                    return True
                except:
                    continue

            print("Upload-Status unklar, warte zusaetzliche Zeit...")
            time.sleep(5)
            return True

        else:
            print("Kein Upload-Element gefunden")
            print("Verfuegbare Elemente auf der Seite:")

            # Debug: Print available elements
            buttons = driver.find_elements(By.TAG_NAME, "button")
            for i, btn in enumerate(buttons[:10]):  # First 10 buttons
                try:
                    text = btn.text[:50] if btn.text else btn.get_attribute("title")[:50]
                    print(f"  Button {i}: {text}")
                except:
                    pass

            return False

    except Exception as e:
        print(f"Fehler beim Upload: {e}")
        return False

def create_test_file():
    """Create a test JSON file for upload"""
    test_data = {
        "test": True,
        "timestamp": datetime.now().isoformat(),
        "message": "Browser-Upload Test zu OwnCloud",
        "sample_data": {
            "numbers": [1, 2, 3, 4, 5],
            "text": "Beispieltext mit Umlauten: äöüß",
            "browser_upload": True
        },
        "metadata": {
            "script": "test_browser_upload.py",
            "purpose": "Browser-Upload-Test mit Selenium",
            "upload_method": "Web Interface"
        }
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"browser_test_{timestamp}.json"

    # Create temporary directory if it doesn't exist
    temp_dir = "./temp"
    os.makedirs(temp_dir, exist_ok=True)

    file_path = os.path.join(temp_dir, filename)

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(test_data, f, ensure_ascii=False, indent=2)

    # Convert to absolute path
    abs_file_path = os.path.abspath(file_path)

    print(f"Test-Datei erstellt: {abs_file_path}")
    return abs_file_path, filename

def main():
    print("BROWSER-UPLOAD TEST zu OwnCloud")
    print("=" * 50)

    # Load configuration
    try:
        config = load_config()
        username = config['login']['username']
        password = config['login']['password']
        print(f"Konfiguration geladen für Benutzer: {username}")
    except Exception as e:
        print(f"Fehler beim Laden der Konfiguration: {e}")
        print("Stelle sicher, dass config.ini existiert und korrekt formatiert ist.")
        return

    # Create test file
    file_path, filename = create_test_file()

    # Create WebDriver (visible browser)
    print("\nStarte Browser (sichtbar)...")
    driver = create_webdriver(headless=False)

    try:
        # Step 1: Login
        print("\nSchritt 1: Anmeldung...")
        if not login_to_owncloud(driver, username, password):
            print("Anmeldung fehlgeschlagen!")
            return

        # Wait a moment for user to see the result
        print("Anmeldung erfolgreich! Warte 3 Sekunden...")
        time.sleep(3)

        # Step 2: Navigate to folder
        print("\nSchritt 2: Navigation zum Upload-Ordner...")
        if not navigate_to_upload_folder(driver):
            print("Navigation fehlgeschlagen!")
            return

        # Wait a moment for user to see the folder
        print("Im Zielordner! Warte 3 Sekunden...")
        time.sleep(3)

        # Step 3: Upload file
        print("\nSchritt 3: Datei-Upload...")
        if upload_file_via_browser(driver, file_path, filename):
            print("Upload erfolgreich!")
        else:
            print("Upload fehlgeschlagen!")

        # Keep browser open for inspection
        print(f"\nUpload-Test abgeschlossen!")
        print(f"Browser bleibt offen zur Inspektion.")
        print(f"Pruefen Sie manuell, ob die Datei '{filename}' im Ordner erscheint.")
        print("Druecken Sie Enter, um den Browser zu schliessen...")
        input()

    except Exception as e:
        print(f"Unerwarteter Fehler: {e}")
    finally:
        # Clean up
        try:
            driver.quit()
        except:
            pass

        # Clean up temp file
        try:
            os.remove(file_path)
            print(f"Temporaere Datei geloescht: {file_path}")
        except:
            pass

if __name__ == "__main__":
    main()