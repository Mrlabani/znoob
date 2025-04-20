import os
import re
import json
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# Get the Terabox credentials from the environment variables
TERABOX_EMAIL = os.getenv("TERABOX_USERNAME")
TERABOX_PASS = os.getenv("TERABOX_PASSWORD")

# Start a session for requests
session = requests.Session()

# Helper function to log into Terabox
def login():
    print("[*] Logging in to Terabox...")
    login_url = "https://www.terabox.com/api/user/login"
    payload = {
        "email": TERABOX_EMAIL,
        "pwd": TERABOX_PASS
    }
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        response = session.post(login_url, headers=headers, data=payload)
        response.raise_for_status()  # Raise an error for bad HTTP response
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Login failed: {e}")
        return None

# Extract file ID and UK from the page HTML
def extract_fid_and_uk(html):
    fid_match = re.search(r'"shareid":(\d+)', html)
    uk_match = re.search(r'"uk":"?(\d+)"?', html)
    if fid_match and uk_match:
        return fid_match.group(1), uk_match.group(1)
    return None, None

# Fetch files in the shared folder
def fetch_folder_files(share_url):
    try:
        r = session.get(share_url, headers={"User-Agent": "Mozilla/5.0"})
        fid, uk = extract_fid_and_uk(r.text)
        if not fid or not uk:
            raise Exception("Could not extract folder ID or user key")
        
        api_url = "https://www.terabox.com/share/list"
        params = {
            "shareid": fid,
            "uk": uk,
            "page": 1,
            "num": 100,
            "order": "filename"
        }
        res = session.get(api_url, params=params)
        res.raise_for_status()  # Ensure response is valid
        data = res.json()
        if "list" not in data:
            raise Exception("Failed to get file list")

        files = []
        for f in data["list"]:
            files.append({
                "name": f["server_filename"],
                "size": f["size"],
                "is_dir": f["isdir"],
                "fs_id": f["fs_id"]
            })
        return files, fid, uk
    except requests.exceptions.RequestException as e:
        print(f"Error fetching folder files: {e}")
        raise
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise

# Generate direct download links for each file
def generate_direct_links(files, share_id, uk):
    links = []
    for f in files:
        dlink_api = "https://www.terabox.com/api/sharedownload"
        payload = {
            "shareid": share_id,
            "uk": uk,
            "product": "share",
            "fid_list": json.dumps([f["fs_id"]])
        }
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.terabox.com/"
        }
        try:
            res = session.post(dlink_api, headers=headers, data=payload)
            res.raise_for_status()  # Ensure the response is valid
            res_json = res.json()
            if "list" in res_json and len(res_json["list"]) > 0:
                dlink = res_json["list"][0].get("dlink")
                links.append({
                    "name": f["name"],
                    "size": f["size"],
                    "direct_link": dlink
                })
        except requests.exceptions.RequestException as e:
            print(f"Error generating direct link for file {f['name']}: {e}")
    return links

# Flask route for extracting Terabox folder contents and links
@app.route("/api/extract", methods=["GET", "POST"])
def extract_api():
    if request.method == "GET":
        link = request.args.get("url")
    else:
        content = request.get_json()
        link = content.get("link") if content else None

    if not link:
        return jsonify({"error": "Missing 'link' parameter in request"}), 400

    # Attempt to log in to Terabox
    login_result = login()
    if not login_result or login_result.get("errno") != 0:
        return jsonify({"error": "Login failed", "details": login_result}), 401

    try:
        # Fetch files and links for the given folder
        files, fid, uk = fetch_folder_files(link)
        final_links = generate_direct_links(files, fid, uk)
        return jsonify({
            "status": "success",
            "total": len(final_links),
            "files": final_links
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
    
