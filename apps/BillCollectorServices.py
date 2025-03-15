# Download file from web service
import time
import os.path
import yaml
import inspect
import threading

from sshkeyboard import listen_keyboard, stop_listening

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from BillCollectorRecipes import CheckRecipe

# Initialize browser and return driver object
# parameterize browser: in debug mode = headless, default download folder, force download by always open pdf externally, ...
def InitBrowser(bcs):
    # browser and webdriver configuration
    homedir = os.path.dirname(os.path.realpath(__file__))
    chrome_options = Options()
    if bcs.dbg == False: chrome_options.add_argument("--headless") # Ensure GUI is off in production
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable_dev-shm-usage")
    chrome_options.binary_location = f"{homedir}/chrome-linux64/chrome"
    prefs = {'download.default_directory' : bcs.dld, "download.prompt_for_download": False, "download.directory_upgrade": True, "plugins.always_open_pdf_externally": True}
    chrome_options.add_experimental_option('prefs', prefs)
    webdriver_service = Service(f"{homedir}/chromedriver-linux64/chromedriver")
    driver = webdriver.Chrome(service=webdriver_service, options=chrome_options)
    return driver

# Debugging functions
#
# Save web page source for debugging if debugging is enabled
def on_debug_save_web_page(bcs):
    if bcs.dbg: save_web_page(bcs.drv)

# Save web page source for debugging
def save_web_page(driver):
    page_source = driver.page_source
    with open('page_source.html', 'w', encoding='utf-8') as f:
        f.write(page_source)
    print("Saved HTML source for debugging.")

# Start keyboard listener if debugging is enabled
def on_debug_start_keyboard_listener(bcs):
    global listener_thread
    if bcs.dbg == True: 
        global pause
        pause = True
        listener_thread = threading.Thread(target=keyboard_listener, daemon=True)
        listener_thread.start()

# Stop keyboard listener if debugging is enabled
def on_debug_stop_keyboard_listener(bcs):
    global listener_thread
    if bcs.dbg == True:
       pause = True
       stop_listening()
       listener_thread.join()

# THREAD - Keyboard listener (space key to pause/resume)
def keyboard_listener():
    def handle_key_press(key):
        global pause
        if key == "space": pause = not pause
    listen_keyboard(on_press=handle_key_press)

# Check for pause for debugging if debugging is enabled
def on_debug_pause_check(bcs):
    if bcs.dbg: pause_check()

# Pause check
def pause_check():
    global pause
    if pause: print ("Paused. Press <SPACE> to resume.")
    while pause: time.sleep(0.1)
    print ("Resume.")
    pause = True # Pause again after resuming

# Service processing controlled by YAML recipe
#
# Service variables
class service_vars:
    def __init__(self, usr, pwd, otp, dbg, dld, yml=None, drv=None):
        self.drv = drv
        self.usr = usr
        self.pwd = pwd
        self.otp = otp
        self.dbg = dbg
        self.dld = dld
        self.yml = yml

# Retrieve file from service - main function
def RetrieveFromService(service, url, user, pwd, otp, test):
    
    bcs = service_vars(user, pwd, otp, test, f"{os.path.dirname(os.path.realpath(__file__))}/Downloads")
    if not os.path.exists(bcs.dld):
        os.makedirs(bcs.dld)
    bcs.drv = InitBrowser(bcs)
    bcs.drv.get(url)

    on_debug_save_web_page(bcs)
    on_debug_start_keyboard_listener(bcs)
    try:
        sname = service.lower().replace(" ", "_")
        bcs.yml = CheckRecipe(f"{os.path.dirname(os.path.realpath(__file__))}/bc-recipes/bc-recipe__{sname}.yaml")
        if bcs.yml == None: raise Exception(f"Recipe {sname} not found.")
        file_downloaded = bc_retrieve(bcs)
        if file_downloaded != None: print(f"Service {service} finished with file {file_downloaded} for {bcs.usr} downloaded.")
        else: print(f"Service {service} for {bcs.usr} finished without a file downloaded.")
    except Exception as e:
        print(f"EXCEPTION in {inspect.currentframe().f_code.co_name}(): {e}")
        print(f"Service {service} for {bcs.usr} not successfully finished.")
        on_debug_stop_keyboard_listener(bcs)
        return False
    else:
        bcs.drv.quit()
        on_debug_stop_keyboard_listener(bcs)
        return True

# Web Element Object
locatorMapping = {
    "XPATH": By.XPATH,
    "ID": By.ID,
    "CSS_SELECTOR": By.CSS_SELECTOR,
    "LINK_TEXT": By.LINK_TEXT
}

class webElementObj:
    class selectorObj:
        def __init__(self, locator, element):
            self.locator = locator
            self.element = element
    def __init__(self, timeout=10, variable=None, graceful=False, key=None):
        self.timeout = timeout
        self.graceful = graceful
        self.variable = variable
        self.key = key

# Retrieve service actions from YAML recipe - helper function
def bc_retrieve(bcs):
    try:
        # Parse the YAML structure
        services = bcs.yml.get('services', [])
        
        for service in services:
                service_name = service.get('serviceName')
                print(f"Processing Service: {service_name}")
                
                actions = service.get('actions', [])
                for action in sorted(actions, key=lambda x: x.get('step', 0)):  # Sort by step number
                    step = action['step']
                    action_type = action['actionType']
                    parameters = action['parameters']
                    
                    print(f"  Executing Step {step}: {action_type}")
                    
                    # Process action based on its type
                    if action_type == "Click":
                        perform_click(bcs, parameters)
                    elif action_type == "ClickShadow":
                        perform_click_shadow(bcs, parameters)
                    elif action_type == "SendKeys":
                        perform_send_keys(bcs, parameters)
                    elif action_type == "Download":
                        file_downloaded = perform_download(bcs, parameters)
                        return file_downloaded
                    else:
                        raise Exception(f"  Unknown action type: {action_type}")
    except Exception as e:
        print(f"EXCEPTION in {inspect.currentframe().f_code.co_name}(): {e}")

# Get Selenium locator
def getSeleniumLocator(locator_type):
    sLocator = locatorMapping.get(locator_type)
    if sLocator is None:
        raise ValueError(f"Unsupported locator type: {locator_type}")
    return sLocator

# Initialize web element object
def initWebElementObj(parameters, expected_locators=1):
    try:
        webElement = webElementObj(timeout = parameters.get('timeout', 10), variable = parameters.get('variable', None), graceful = parameters.get('graceful', False))
        webElement.selectors = []
        locators = parameters.get('locators', [])
        if len(locators) != expected_locators:
            raise Exception(f"Expected {expected_locators} locators, but got {len(locators)}")
        for locator in locators:
            seleniumLocator = getSeleniumLocator(locator.get('locatorType'))
            element = locator.get('element')
            if seleniumLocator and element:
                selector = webElementObj.selectorObj(seleniumLocator, element)
                webElement.selectors.append(selector)
            else:
                raise Exception(f"Missing locatorType or element in {locator}")
            print(f"      Locator: {seleniumLocator}, Element: {element}")    
        return webElement
    except Exception as e:
        print(f"EXCEPTION in {inspect.currentframe().f_code.co_name}(): {e}")
        return None

def perform_click(bcs, parameters):
    try:
        print(f"    Clicking on DOM element with the following selectors:")
        webElement = initWebElementObj(parameters, 1)
        tryClick(bcs, webElement)
    except Exception as e:
        print(f"EXCEPTION in {inspect.currentframe().f_code.co_name}(): {e}")

def perform_click_shadow(bcs, parameters):
    try:
        print(f"    Clicking on shadow DOM elements with the following selectors:")
        webElement = initWebElementObj(parameters, 3)
        tryClickShadow(bcs, webElement)
    except Exception as e:
        print(f"EXCEPTION in {inspect.currentframe().f_code.co_name}(): {e}")


def perform_send_keys(bcs, parameters):
    try:
        print(f"    Sending keys to elements with the following selectors:")
        webElement = initWebElementObj(parameters)
        if webElement.variable == "{USERNAME}":
            webElement.key = bcs.usr
        elif webElement.variable == "{PASSWORD}":
            webElement.key = bcs.pwd
        elif webElement.variable == "{OTP}":
            webElement.key = bcs.otp
        elif webElement.variable == "Keys.ENTER":
            webElement.key = Keys.ENTER
        else:
            raise Exception(f"    Unbekannte Variable: {webElement.variable}")
        trySendKeys(bcs, webElement)
    except Exception as e:
        print(f"EXCEPTION in {inspect.currentframe().f_code.co_name}: {e}")

def perform_download(bcs, parameters):
    try:
        print(f"    Performing download action with the following selectors:")
        webElement = initWebElementObj(parameters, 1)
        file_downloaded = tryDownload(bcs, webElement)
        return file_downloaded
    except Exception as e:
        print(f"EXCEPTION in {inspect.currentframe().f_code.co_name}(): {e}")

# Try to click element which needs time to be ready
def tryClick(bcs, we):
    Timeout = we.timeout
    on_debug_save_web_page(bcs)
    on_debug_pause_check(bcs)
    while Timeout > 0:
        try:
            bcs.drv.find_element(we.selectors[0].locator, we.selectors[0].element).click()
        except: 
            time.sleep(1)
            Timeout -= 1
        else:
            return True
    if we.graceful == False: raise RuntimeError(f"Element loading timeout") 
    else: return False

# Try to click shadow element which needs time to be ready
def tryClickShadow(bcs, we):
    try:
        shadow_host = WebDriverWait(bcs.drv, we.timeout).until(EC.presence_of_element_located((we.selectors[0].locator, we.selectors[0].element)))
        shadow_root = bcs.drv.execute_script('return arguments[0].shadowRoot', shadow_host)
        WebDriverWait(shadow_root, we.timeout).until(EC.presence_of_element_located((we.selectors[1].locator, we.selectors[1].element)))
        cookie_button = shadow_root.find_element(we.selectors[2].locator, we.selectors[2].element)
        bcs.drv.execute_script("arguments[0].click();", cookie_button)
    except TimeoutException as e:
        on_debug_save_web_page(bcs)
        print(f"EXCEPTION in {inspect.currentframe().f_code.co_name}(): Timeout: Element konnte nicht gefunden werden.")
    except NoSuchElementException as e:
        on_debug_save_web_page(bcs)
        print(f"EXCEPTION in {inspect.currentframe().f_code.co_name}(): Element nicht vorhanden.")
    except Exception as e:
        on_debug_save_web_page(bcs)
        print(f"EXCEPTION in {inspect.currentframe().f_code.co_name}(): {e}")
    else:
        on_debug_save_web_page(bcs)
        return True

# Try to send keys to element which needs time to be ready
def trySendKeys(bcs, we):
    Timeout = we.timeout
    on_debug_save_web_page(bcs)
    while Timeout > 0:
        try:
             bcs.drv.find_element(we.selectors[0].locator, we.selectors[0].element).send_keys(we.key)
        except: 
            time.sleep(1)
            Timeout -= 1
        else:
            return True
    if we.graceful == False: raise RuntimeError(f"Sending Key to Element timeout")
    else: return False

# Try to download file from element which needs time to be ready
# Checks download folder for new downloaded file and returns the name of the downloaded file
def tryDownload(bcs, we):
    prev_file = latest_download_file(bcs.dld)
    tryClick(bcs,we)
    time.sleep(5)
    return is_download_finished(bcs.dld, prev_file)
    
def latest_download_file(download_dir):
      os.chdir(download_dir)
      files = sorted(os.listdir(os.getcwd()), key=os.path.getmtime)
      if len(files) > 0: latest_f = files[-1]
      else: latest_f = None
      return latest_f

def is_download_finished(download_dir, previous_file):
    current_file = latest_download_file(download_dir)
    if current_file != previous_file:
        return current_file
    else:
        return None
