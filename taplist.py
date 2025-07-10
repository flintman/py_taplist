import os
import requests
import json
import xml.etree.ElementTree as ET
import threading
import time
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, request, session, redirect, url_for, flash

class TaplistApp:
    CONFIG_FILE = "config.json"
    BEER_FILE = "beers.xml"

    def __init__(self):
        self.app = Flask(__name__)
        # Set a secret key for sessions
        self.app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'your-secret-key-change-this')
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        self.config = self.load_config()
        self.title = self.config.get("title", "Enter your Title Here")
        
        # Get API key from environment variable first, then config file
        self.api_key = os.environ.get('BREWERS_FRIEND_API_KEY') or self.config.get("api_key", "Enter API key")
        
        self.selected_theme = self.config.get("selected_theme", "theme_one")
        self.selected_theme_style = self.config.get("selected_theme_style", "light")
        self.refresh_interval = int(self.config.get("refresh_interval", 3600))
        self.admin_password = self.config.get("admin_password", "admin")  # Default password
        self.folders = self.config.get("folders", [])
        
        # Cache for beer data
        self.cached_beers = []
        self.last_fetch_time = None
        self.cache_lock = threading.Lock()
        self.polling_active = False
        
        # Start background polling thread
        self.start_background_polling()

        # Define routes
        self.app.add_url_rule("/", "taplist", view_func=self.taplist)
        self.app.add_url_rule("/admin", "admin", view_func=self.admin, methods=["GET", "POST"])
        self.app.add_url_rule("/admin/login", "admin_login", view_func=self.admin_login, methods=["GET", "POST"])
        self.app.add_url_rule("/admin/logout", "admin_logout", view_func=self.admin_logout)
    
    def load_config(self):
        if os.path.exists(self.CONFIG_FILE):
            with open(self.CONFIG_FILE, "r") as file:
                config = json.load(file)
                # Remove API key from config file if it exists, we'll use env var
                if "api_key" in config and config["api_key"] != "Enter API key":
                    self.logger.warning("API key found in config file. Consider moving to environment variable BREWERS_FRIEND_API_KEY")
                return config
        return {
            "title": "Enter your Title Here", 
            "selected_theme": "theme_one", 
            "selected_theme_style": "light",
            "refresh_interval": 3600,
            "admin_password": "admin",
            "folders": [],
            "selected_folders": []
        }

    def save_config(self):
        # Don't save API key to config file if it's set via environment variable
        config_to_save = self.config.copy()
        if os.environ.get('BREWERS_FRIEND_API_KEY'):
            config_to_save.pop("api_key", None)
            
        with open(self.CONFIG_FILE, "w") as file:
            json.dump(config_to_save, file, indent=4)
        self.config = self.load_config()

    def start_background_polling(self):
        """Start the background thread for polling API data."""
        if not self.polling_active:
            self.polling_active = True
            thread = threading.Thread(target=self._background_poll, daemon=True)
            thread.start()
            self.logger.info("Background polling thread started")

    def _background_poll(self):
        """Background thread function to poll API data at intervals."""
        while self.polling_active:
            try:
                if self.api_key and self.api_key != "Enter API key":
                    self._fetch_and_cache_beers()
                time.sleep(self.refresh_interval)
            except Exception as e:
                self.logger.error(f"Error in background polling: {e}")
                time.sleep(60)  # Wait 1 minute before retrying on error

    def _fetch_and_cache_beers(self):
        """Fetch beer data from API and cache it."""
        selected_folders = self.config.get("selected_folders", [])
        if not selected_folders:
            return

        try:
            self.logger.info("Fetching beer data from API...")
            beers = self._fetch_beers_from_api()
            
            with self.cache_lock:
                self.cached_beers = beers
                self.last_fetch_time = datetime.now()
            
            # Also save to XML file for persistence
            if beers:
                self._save_beers_to_xml(beers)
            
            self.logger.info(f"Successfully cached {len(beers)} beers")
        except Exception as e:
            self.logger.error(f"Error fetching and caching beers: {e}")

    def _fetch_beers_from_api(self):
        """Fetch beers from the API (optimized version)."""
        if not self.api_key or self.api_key == "Enter API key":
            return []

        selected_folders = self.config.get("selected_folders", [])
        if not selected_folders:
            return []

        try:
            url = "https://api.brewersfriend.com/v1/brewsessions"
            headers = {"X-API-KEY": self.api_key}
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            brewsessions = response.json().get("brewsessions", [])

            # Filter sessions by selected folders first
            filtered_sessions = [
                session for session in brewsessions 
                if session.get("folder_name") in selected_folders
            ]

            beers = []
            # Batch the detailed requests
            for session in filtered_sessions:
                try:
                    brew_id = session.get("id")
                    if not brew_id:
                        continue
                        
                    brew_url = f"https://api.brewersfriend.com/v1/brewsessions/{brew_id}"
                    brew_response = requests.get(brew_url, headers=headers, timeout=15)
                    brew_response.raise_for_status()
                    brew_data = brew_response.json().get("brewsessions", [])[0]

                    if brew_data:
                        recipe = brew_data.get("recipe", {})
                        beers.append({
                            "title": str(recipe.get("title", "Unknown"))[:100],  # Limit length
                            "stylename": str(recipe.get("stylename", "Unknown"))[:50],
                            "abv_alt": min(float(brew_data.get("current_stats", {}).get("abv_alt", 0)), 50.0),  # Cap at 50%
                            "ibutinseth": min(int(recipe.get("ibutinseth", 0)), 200),  # Cap at 200 IBU
                            "srmmorey": min(int(recipe.get("srmmorey", 0)), 80),  # Cap at 80 SRM
                            "userdate": str(brew_data.get("userdate", "Unknown"))[:20],
                            "id": int(recipe.get("id", 0)),
                        })
                except Exception as e:
                    self.logger.warning(f"Error fetching brew session {brew_id}: {e}")
                    continue

            return beers
        except Exception as e:
            self.logger.error(f"Error fetching beers from API: {e}")
            return []

    def _save_beers_to_xml(self, beers):
        """Save beers to XML file."""
        try:
            root = ET.Element("beers")
            for beer in beers:
                beer_elem = ET.SubElement(root, "beer")
                for key, value in beer.items():
                    elem = ET.SubElement(beer_elem, key)
                    # Escape XML content
                    elem.text = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            
            tree = ET.ElementTree(root)
            tree.write(self.BEER_FILE, encoding="utf-8", xml_declaration=True)
        except Exception as e:
            self.logger.error(f"Error saving beers to XML: {e}")

    def get_cached_beers(self):
        """Get cached beer data."""
        with self.cache_lock:
            if self.cached_beers:
                return self.cached_beers.copy()
            
        # Fallback to loading from XML file if cache is empty
        return self.load_beers()

    def admin_login(self):
        """Handle admin login."""
        if request.method == "POST":
            password = request.form.get("password", "").strip()
            if password == self.admin_password:
                session["admin_authenticated"] = True
                flash("Login successful!", "success")
                return redirect(url_for("admin"))
            else:
                flash("Invalid password!", "error")
        
        return render_template(
            f"{self.selected_theme}/admin_login.html",
            selected_theme=self.selected_theme,
            selected_theme_style=self.selected_theme_style
        )

    def admin_logout(self):
        """Handle admin logout."""
        session.pop("admin_authenticated", None)
        flash("Logged out successfully!", "info")
        return redirect(url_for("taplist"))

    def require_admin_auth(self):
        """Check if admin is authenticated."""
        return session.get("admin_authenticated", False)


    def load_beers(self):
        if not os.path.exists(self.BEER_FILE):
            return []
        
        tree = ET.parse(self.BEER_FILE)
        root = tree.getroot()
        beers = []
        for beer in root.findall("beer"):
            beers.append({
                "title": beer.find("title").text,
                "stylename": beer.find("stylename").text,
                "abv_alt": float(beer.find("abv_alt").text),
                "ibutinseth": int(beer.find("ibutinseth").text),
                "srmmorey": int(beer.find("srmmorey").text),
                "userdate": beer.find("userdate").text,
                "id": int(beer.find("id").text),
            })
        return beers

    def srm_color(self, srm):
        # Map SRM values to colors
        srm_colors = {
            1: '#FEEFB3', 2: '#FDD49E', 3: '#FDBB84',
            4: '#FDB168', 5: '#E9A84F', 6: '#E38F3D',
            7: '#DB7C26', 8: '#C96E1F', 10: '#BE5B1F',
            13: '#A84D15', 17: '#8E3E10', 20: '#7C2D12',
            30: '#6B1E14', 999: '#5A0E16'
        }

        # Iterate through the SRM thresholds and return the appropriate color
        for limit, color in srm_colors.items():
            if srm <= limit:
                return color

        # Default color for very high SRM values
        return '#5A0E16'

    def taplist(self):
        # Use cached data instead of fetching from API
        beers = self.get_cached_beers()

        message = None
        if self.api_key == "Enter API key":
            message = "No API available. Try adding API and select a folder."
        elif not beers and self.api_key != "Enter API key":
            message = "No beers available. Try adding some to your selected folders."

        # Add cache status info
        cache_status = ""
        if self.last_fetch_time:
            time_since_update = datetime.now() - self.last_fetch_time
            cache_status = f"Last updated: {time_since_update.seconds // 60} minutes ago"

        return render_template(
            f"{self.selected_theme}/taplist.html",
            beers=beers,
            srm_color=self.srm_color,
            title=self.title,
            message=message,
            cache_status=cache_status,
            selected_theme=self.selected_theme,
            selected_theme_style=self.selected_theme_style,
            refresh_interval=self.refresh_interval
        )


    def admin(self):
        # Check authentication
        if not self.require_admin_auth():
            return redirect(url_for("admin_login"))
            
        message = None

        if request.method == "POST":
            message = ""
            
            # Validate and sanitize inputs
            if "title" in request.form:
                title = request.form.get("title", "").strip()[:100]  # Limit length
                if title:
                    self.title = title
                    self.config["title"] = self.title
            
            if "available_folders" in request.form:
                selected_items = request.form.getlist("available_folders")
                # Validate folder names
                selected_items = [item.strip()[:50] for item in selected_items if item.strip()]
                current_selected_folders = self.config.get("selected_folders", [])
                updated_selected_folders = list(set(current_selected_folders + selected_items))
                self.config["selected_folders"] = updated_selected_folders

            if "selected_folders" in request.form:
                selected_items = request.form.getlist("selected_folders")
                selected_items = [item.strip()[:50] for item in selected_items if item.strip()]
                current_selected_folders = self.config.get("selected_folders", [])
                updated_selected_folders = [folder for folder in current_selected_folders if folder not in selected_items]
                self.config["selected_folders"] = updated_selected_folders
                if not self.config["selected_folders"]:
                    self.clear_beers_file()

            if "admin_password" in request.form:
                new_password = request.form.get("admin_password", "").strip()
                if len(new_password) >= 4:  # Minimum password length
                    self.admin_password = new_password
                    self.config["admin_password"] = self.admin_password
                    message += "Admin password updated successfully.\n"
                else:
                    message += "Password must be at least 4 characters long.\n"

            if "refresh_interval" in request.form:
                try:
                    new_refresh_interval = int(request.form.get("refresh_interval", "3600"))
                    if 60 <= new_refresh_interval <= 86400:  # Between 1 minute and 1 day
                        self.refresh_interval = new_refresh_interval
                        self.config["refresh_interval"] = self.refresh_interval
                        message += "Refresh interval updated successfully.\n"
                    else:
                        message += "Refresh interval must be between 60 and 86400 seconds.\n"
                except ValueError:
                    message += "Invalid refresh interval value.\n"

            if "theme" in request.form:
                selected_theme = request.form.get("theme", "").strip()
                if selected_theme in ["theme_one", "theme_two"]:  # Validate theme
                    self.config["selected_theme"] = selected_theme
                    self.selected_theme = selected_theme

            if "theme_style" in request.form:
                selected_theme_style = request.form.get("theme_style", "").strip()
                if selected_theme_style in ["light", "dark"]:  # Validate theme style
                    self.config["selected_theme_style"] = selected_theme_style
                    self.selected_theme_style = selected_theme_style

            # Force refresh of folders and beer data
            all_folders = self.fetch_folders_from_api()
            if all_folders:
                self.folders = all_folders
                self.config["folders"] = self.folders
                # Trigger immediate background refresh
                threading.Thread(target=self._fetch_and_cache_beers, daemon=True).start()
                message += "Folders refreshed successfully.\n"
            elif self.api_key and self.api_key != "Enter API key":
                message += "Error refreshing folders. Please check API key.\n"

            self.save_config()
            message += "Changes saved successfully."

        all_folders = self.fetch_folders_from_api()
        selected_folders = self.config.get("selected_folders", [])
        unselected_folders = [folder for folder in all_folders if folder not in selected_folders]

        return render_template(
            f"{self.selected_theme}/admin.html",
            title=self.title,
            api_key_status="Set via environment variable" if os.environ.get('BREWERS_FRIEND_API_KEY') else "Not set",
            selected_theme=self.selected_theme,
            selected_theme_style=self.selected_theme_style,
            selected_folders=selected_folders,
            unselected_folders=unselected_folders,
            message=message,
            refresh_interval=self.refresh_interval
        )

    def fetch_folders_from_api(self):
        if not self.api_key or self.api_key == "Enter API key":
            return []

        try:
            url = "https://api.brewersfriend.com/v1/brewsessions"
            headers = {"X-API-KEY": self.api_key}
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            brewsessions = response.json().get("brewsessions", [])
            folders = list({session.get("folder_name") for session in brewsessions if session.get("folder_name")})
            return sorted(folders)  # Sort for consistency
        except Exception as e:
            self.logger.error(f"Error fetching folders: {e}")
            return []

    def clear_beers_file(self):
        """Clear the beers XML file and cache."""
        try:
            with open(self.BEER_FILE, "w") as file:
                file.write("<beers></beers>")
            
            with self.cache_lock:
                self.cached_beers = []
                self.last_fetch_time = None
                
        except Exception as e:
            self.logger.error(f"Error clearing beers file: {e}")

    def run(self):
        """Run the Flask app."""
        self.app.run(host="0.0.0.0", port=5000, debug=False)  # Disable debug in production

if __name__ == "__main__":
    app = TaplistApp()
    app.run()
