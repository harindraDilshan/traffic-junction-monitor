from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
from datetime import datetime
import os
import io
import json
import re
import math
import schedule
import sys
# Replace pydrive2 imports with Google API Client libraries
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2 import service_account

def setup_google_drive():
    """Set up Google Drive with Service Account credentials."""
    try:
        # Path to your service account JSON file
        SERVICE_ACCOUNT_FILE = 'client_secrets.json'
        
        # Define the scopes needed
        SCOPES = ['https://www.googleapis.com/auth/drive']
        
        # Create credentials using the service account file
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        
        # Build the Drive service
        drive_service = build('drive', 'v3', credentials=credentials)
        
        print("Google Drive service account authentication successful!")
        return drive_service
    
    except Exception as e:
        print(f"Error setting up Google Drive service account: {e}")
        return None

def check_permissions(drive_service, folder_id):
    """Check permissions on a folder to ensure the service account can write to it."""
    try:
        # Get the existing permissions
        permissions = drive_service.permissions().list(fileId=folder_id).execute()
        print(f"Current permissions for folder {folder_id}: {permissions}")
        
        # Log the folder details
        folder = drive_service.files().get(fileId=folder_id, fields='id,name,owners,shared').execute()
        print(f"Folder details: {folder}")
        
        return True
    except Exception as e:
        print(f"Error checking permissions: {e}")
        return False

def get_or_create_folder(drive_service, folder_name):
    """Get or create a folder in Google Drive using service account."""
    try:
        # Check if folder exists
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        folders = results.get('files', [])
        
        if folders:
            folder_id = folders[0]['id']
            print(f"Found existing folder: {folder_name} with ID: {folder_id}")
            # Check permissions on existing folder
            check_permissions(drive_service, folder_id)
            return folder_id
        else:
            # Create folder if it doesn't exist
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = drive_service.files().create(body=folder_metadata, fields='id').execute()
            folder_id = folder.get('id')
            print(f"Created new folder: {folder_name} with ID: {folder_id}")
            
            # Make sure the folder is visible to you (assuming you own the Drive)
            try:
                your_email = "youremail@gmail.com"  # Replace with your email
                permission = {
                    'type': 'user',
                    'role': 'writer',
                    'emailAddress': your_email
                }
                drive_service.permissions().create(
                    fileId=folder_id,
                    body=permission,
                    sendNotificationEmail=False
                ).execute()
                print(f"Added explicit permission for {your_email} to folder {folder_name}")
            except Exception as e:
                print(f"Error adding permission to folder: {e}")
            
            return folder_id
    
    except Exception as e:
        print(f"Error getting or creating folder: {e}")
        return None

def handle_google_consent(driver, wait):
    """Comprehensive method to handle Google consent popups in multiple languages."""
    consent_selectors = [
        # German consent buttons
        "button:contains('Alle akzeptieren')",
        "button[aria-label='Alle akzeptieren']",
        "div[role='button']:contains('Alle akzeptieren')",
        
        # English consent buttons
        "button:contains('Accept all')",
        "button[aria-label='Accept all']",
        
        # Potential XPath alternatives
        "//button[contains(text(), 'Alle akzeptieren')]",
        "//button[contains(text(), 'Accept all')]",
        
        # More generic selectors
        "#L2AGLb button",  # Known Google consent button class
        "div[role='dialog'] button"
    ]
    
    for selector in consent_selectors:
        try:
            # Try CSS selector first
            if selector.startswith('//'):
                consent_button = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
            else:
                consent_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
            
            # Use JavaScript click to ensure it works in all scenarios
            driver.execute_script("arguments[0].click();", consent_button)
            time.sleep(2)  # Wait for page to process
            print(f"Consent handled with selector: {selector}")
            return True
        except Exception as e:
            continue
    
    print("Could not find consent button")
    return False

def capture_google_maps_traffic(lat, lng, zoom=18, location_name=None, drive_service=None, folder_id=None):
    # Set up Chrome options for headless mode with additional configurations
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")  # Enable headless mode
    chrome_options.add_argument("--window-size=1920,1080")  # Ensure full resolution screenshot
    chrome_options.add_argument("--disable-gpu")  # Improve performance in headless mode
    chrome_options.add_argument("--no-sandbox")  # Helps in some environments
    chrome_options.add_argument("--disable-dev-shm-usage")  # Prevents issues with shared memory
    
    # Add more browser fingerprinting to avoid detection
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Set up the driver with explicit wait
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    # Configure explicit waits
    wait = WebDriverWait(driver, 20)
    
    try:
        # Navigate to Google Maps with traffic layer
        driver.get(f"https://www.google.com/maps/@{lat},{lng},{zoom}z/data=!5m1!1e1")
        
        # Handle potential consent page
        handle_google_consent(driver, wait)
        
        # Wait for map to load
        print(f"Waiting for map to load for location: {location_name if location_name else f'{lat}, {lng}'}...")
        time.sleep(10)  # Increased wait time for better loading
        
        # Calculate viewport size
        viewport_size = driver.execute_script("""
            return {
                width: window.innerWidth || document.documentElement.clientWidth,
                height: window.innerHeight || document.documentElement.clientHeight
            };
        """)
        
                # Remove UI elements from the map using JavaScript
        js_code = """
        // Hide search box with multiple selectors
        var searchSelectors = [
            '.searchbox',
            '.searchbox-shadow',
            '.widget-pane',
            '.omnibox-container',
            '.searchbox-searchbutton',
            '.searchbox-directions-button',
            'input[aria-label="Search Google Maps"]',
            'div[aria-label="Search Google Maps"]',
            'div[jsaction*="search"]',
            'div[jsaction*="pane.togglePane"]',
            'div[jsaction*="query"]',
            'div[data-placeholder="Search Google Maps"]',
            'div[role="search"]',
            'div.gsfi',
            'div.gstl_50'
        ];
        
        searchSelectors.forEach(function(selector) {
            var elements = document.querySelectorAll(selector);
            elements.forEach(function(el) {
                if (el) {
                    el.style.display = 'none';
                    el.style.visibility = 'hidden';
                    el.style.opacity = '0';
                    el.style.pointerEvents = 'none';
                }
            });
        });
        
        // Hide all other UI elements
        var otherElements = document.querySelectorAll('.widget-settings-button, .app-viewcard-strip, ' +
            '.navigation-control, .watermark, .ml-promotion-action-button, ' +
            '.widget-settings, .watermark, .navigation-controls-directions, ' +
            '.google-maps-link, .google-logo, .terms-dialog, ' +
            '.scene-footer, .app-bottom-content-anchor, .compass-container, .dryRY,' + '.E9Z7uf, .waCXA, .QRc3, .Tn5ygd,' + '.gb_Zd, .gb_Mf, .gb_0, .gb_Lf, .gb_ka');
            
        otherElements.forEach(function(el) {
            if (el) {
                el.style.display = 'none';
                el.style.visibility = 'hidden';
            }
        });
        
        // Remove map labels
        var mapLabels = document.querySelectorAll('.map-label, .gm-style-text, .poi-info-window');
        mapLabels.forEach(function(el) {
            if (el) el.style.display = 'none';
        });
        
        // Check for top-level containers that might contain the search box
        var topContainers = document.querySelectorAll('div[role="complementary"], div[role="main"] > div');
        topContainers.forEach(function(container) {
            if (container && container.querySelector('input') && container.offsetHeight < 100) {
                container.style.display = 'none';
            }
        });
        """
        driver.execute_script(js_code)
        
        # Take screenshot
        screenshot_png = driver.get_screenshot_as_png()
        
        # Prepare metadata
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        location_suffix = f"_{location_name}" if location_name else f"_{lat}_{lng}"
        
        # Upload to Google Drive if drive connection is available
        if drive_service and folder_id:
            file_name = f'traffic_{timestamp}{location_suffix}.png'
            
            # Check folder permissions first
            check_permissions(drive_service, folder_id)
            
            # Create file metadata with explicit visibility
            file_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }
            
            # Create media
            media = MediaIoBaseUpload(
                io.BytesIO(screenshot_png),
                mimetype='image/png',
                resumable=True
            )
            
            # Upload file
            file = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,webViewLink',
                supportsAllDrives=True
            ).execute()
            
            print(f"Uploaded screenshot for {location_name}. File ID: {file.get('id')}")
            print(f"File link: {file.get('webViewLink', 'No link available')}")
            
            # Make sure the file is visible to you (assuming you own the Drive)
            try:
                your_email = "youremail@gmail.com"  # Replace with your email
                permission = {
                    'type': 'user',
                    'role': 'reader',
                    'emailAddress': your_email
                }
                drive_service.permissions().create(
                    fileId=file.get('id'),
                    body=permission,
                    sendNotificationEmail=False
                ).execute()
                print(f"Added explicit permission for {your_email} to file {file_name}")
            except Exception as e:
                print(f"Error adding permission to file: {e}")
        
    except Exception as e:
        print(f"Error while processing location {location_name if location_name else f'{lat}, {lng}'}: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Ensure browser is closed
        driver.quit()

def capture_multiple_locations(coordinates, zoom=18, location_names=None, drive_service=None, folder_id=None):
    """
    Capture screenshots for multiple locations.
    
    Args:
        coordinates: List of (lat, lng) tuples
        zoom: Zoom level for all screenshots
        location_names: Optional list of location names (same length as coordinates)
        drive_service: Google Drive service
        folder_id: Google Drive folder ID
    """
    print(f"Starting to capture {len(coordinates)} locations...")
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Current time: {current_time}")
    
    for i, (lat, lng) in enumerate(coordinates):
        location_name = location_names[i] if location_names and i < len(location_names) else f"location_{i+1}"
        print(f"Processing location {i+1}/{len(coordinates)}: {location_name} ({lat}, {lng})")
        capture_google_maps_traffic(lat, lng, zoom, location_name, drive_service, folder_id)
        
        # Wait between screenshots to avoid overwhelming the system
        if i < len(coordinates) - 1:
            print("Waiting 5 seconds before next location...")
            time.sleep(5)
    
    print("All locations have been processed!")

def job():
    """Function to run on schedule."""
    print(f"Starting scheduled job at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Set up Google Drive connection with service account
    drive_service = setup_google_drive()
    
    if drive_service:
        # Get today's date for folder organization
        today_folder_name = datetime.now().strftime("Traffic_Data_%Y%m%d")
        folder_id = get_or_create_folder(drive_service, today_folder_name)
        
        if folder_id:
            print(f"Using Google Drive folder: {today_folder_name} with ID: {folder_id}")
        else:
            print("Failed to get or create folder")
            return  # Exit if no folder
    else:
        print("Google Drive integration not available")
        return  # Exit if no Google Drive connection
    
    # List of coordinates (lat, lng)
   
    coordinates = [(9.917399, 99.868425), (1.915214, 79.893217), (6.922508, 39.867205), (9.919359, 99.965598), (8.914790, 96.863834), (7.989839, 78.871143)]
    
    # Optional: Give names to locations for better file organization
    location_names = ['location_1', 'location_2', 'location_3', 'location_4', 'location_5', 'location_6']
    
    # Capture screenshots for all locations
    capture_multiple_locations(coordinates, zoom=18, location_names=location_names, drive_service=drive_service, folder_id=folder_id)

def run_continuously():
    """Run the job continuously with the scheduler."""
    # Schedule to run every 15 minutes
    schedule.every(15).minutes.do(job)
    
    # Run once immediately when starting
    job()
    
    # Keep the script running
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    print("Starting automated traffic monitoring script")
    print("Press Ctrl+C to exit")
    
    try:
        run_continuously()
    except KeyboardInterrupt:
        print("Exiting script by user request")
        sys.exit(0)
    except Exception as e:
        print(f"Script encountered an error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)