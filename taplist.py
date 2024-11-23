import os
import requests
import json
import xml.etree.ElementTree as ET
from flask import Flask, render_template, request

class TaplistApp:
    CONFIG_FILE = "config.json"
    BEER_FILE = "beers.xml"

    def __init__(self):
        self.app = Flask(__name__)
        self.config = self.load_config()
        self.title = self.config.get("title", "Enter your Title Here")
        self.api_key = self.config.get("api_key", "Enter API key")
        self.selected_theme = self.config.get("selected_theme", "light")
        self.folders = self.config.get("folders", [])
        self.beers = []

        # Define routes
        self.app.add_url_rule("/", view_func=self.taplist)
        self.app.add_url_rule("/admin", view_func=self.admin, methods=["GET", "POST"])
    
    def load_config(self):
        if os.path.exists(self.CONFIG_FILE):
            with open(self.CONFIG_FILE, "r") as file:
                return json.load(file)
        return {"api_key": "Enter API key", "title": "Enter your Title Here", "selected_theme": "light", "folders": []}

    def save_config(self):
        with open(self.CONFIG_FILE, "w") as file:
            json.dump(self.config, file, indent=4)
        self.config = self.load_config()


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
        self.fetch_beers_by_folder()
        self.beers = self.load_beers()

        message = None
        if self.api_key == "Enter API key":
             message = "No API available. Try adding API and select a folder."
        elif not self.beers and self.api_key != "Enter API key":
            message = "No beers available. Try adding some to your selected folders."

        return render_template(
            f"themes/{self.selected_theme}/taplist.html",
            beers=self.beers,
            srm_color=self.srm_color,
            title=self.title,
            message=message
        )


    def admin(self):
        message = None

        if request.method == "POST":
            message = ""
            if "title" in request.form:
                self.title = request.form.get("title", self.title)
                self.config["title"] = self.title
            
            if "available_folders" in request.form:
                selected_items = request.form.getlist("available_folders")
                current_selected_folders = self.config.get("selected_folders", [])
                updated_selected_folders = list(set(current_selected_folders + selected_items))
                self.config["selected_folders"] = updated_selected_folders

            if "selected_folders" in request.form:
                selected_items = request.form.getlist("selected_folders")
                current_selected_folders = self.config.get("selected_folders", [])
                updated_selected_folders = [folder for folder in current_selected_folders if folder not in selected_items]
                self.config["selected_folders"] = updated_selected_folders
                if not self.config["selected_folders"]:
                    self.clear_beers_file()

            if "api_key" in request.form:
                new_api_key = request.form.get("api_key", "").strip()
                if new_api_key != self.api_key:
                    self.api_key = new_api_key
                    self.config["api_key"] = self.api_key

            if "theme" in request.form:
                selected_theme = request.form.get("theme", "").strip()
                self.config["selected_theme"] = selected_theme
                self.selected_theme = selected_theme

            all_folders = self.fetch_folders_from_api()
            if all_folders:
                self.folders = all_folders
                self.config["folders"] = self.folders
                message += "API key updated successfully, and folders refreshed.\n"
            else:
                message += "Invalid API key. Please check and try again.\n"


            self.save_config()
            message += "Changes saved successfully."

        all_folders = self.fetch_folders_from_api()

        selected_folders = self.config.get("selected_folders", [])
        unselected_folders = [folder for folder in all_folders if folder not in selected_folders]

        return render_template(
            f"themes/{self.selected_theme}/admin.html",
            title=self.title,
            api_key=self.api_key,
            selected_theme=self.selected_theme,
            selected_folders=selected_folders,
            unselected_folders=unselected_folders,
            message=message
        )

    def fetch_folders_from_api(self):
        if not self.api_key:
            return []

        try:
            url = "https://api.brewersfriend.com/v1/brewsessions"
            headers = {"X-API-KEY": self.api_key}
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            brewsessions = response.json().get("brewsessions", [])
            return list({session.get("folder_name") for session in brewsessions if session.get("folder_name")})
        except Exception as e:
            print(f"Error fetching folders: {e}")
            return []

    def fetch_beers_by_folder(self):
        if not self.api_key:
            return []

        selected_folders = self.config.get("selected_folders", [])
        if not selected_folders:
            return []

        try:
            url = "https://api.brewersfriend.com/v1/brewsessions"
            headers = {"X-API-KEY": self.api_key}
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            brewsessions = response.json().get("brewsessions", [])

            beers = []
            for session in brewsessions:
                if session.get("folder_name") in selected_folders:
                    brew_id = session.get("id")
                    brew_url = f"https://api.brewersfriend.com/v1/brewsessions/{brew_id}"
                    brew_response = requests.get(brew_url, headers=headers)
                    brew_response.raise_for_status()
                    brew_data = brew_response.json().get("brewsessions", [])[0]

                    if brew_data:
                        recipe = brew_data.get("recipe", {})
                        beers.append({
                            "title": recipe.get("title", "Unknown"),
                            "stylename": recipe.get("stylename", "Unknown"),
                            "abv_alt": float(brew_data.get("current_stats", {}).get("abv_alt", 0)),
                            "ibutinseth": int(recipe.get("ibutinseth", 0)),
                            "srmmorey": int(recipe.get("srmmorey", 0)),
                            "userdate": brew_data.get("userdate", "Unknown"),
                            "id": int(recipe.get("id", 0)),
                        })

            if beers:
                root = ET.Element("beers")
                for beer in beers:
                    beer_elem = ET.SubElement(root, "beer")
                    for key, value in beer.items():
                        elem = ET.SubElement(beer_elem, key)
                        elem.text = str(value)
                
                tree = ET.ElementTree(root)
                tree.write(self.BEER_FILE, encoding="utf-8", xml_declaration=True)

            return beers
        except Exception as e:
            print(f"Error fetching beers: {e}")
            return []

    def clear_beers_file(self):
        if os.path.exists(self.BEER_FILE):
            with open(self.BEER_FILE, "w") as file:
                file.write("<beers></beers>")

    def run(self):
        """Run the Flask app."""
        self.app.run(debug=True)

if __name__ == "__main__":
    app = TaplistApp()
    app.run()
