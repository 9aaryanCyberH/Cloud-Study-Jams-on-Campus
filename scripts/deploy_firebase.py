"""Deploy CloudPort static landing page directly to Google Firebase Hosting (Free Tier, No Billing)."""
import hashlib
import json
import os
import subprocess
import sys
import urllib.request

GCLOUD = r"C:\Users\Aaryan Kumar\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
PROJECT_ID = "cloud-study-jams-3f931"
SITE_ID = "cloud-study-jams-3f931"
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

def get_access_token():
    print("[1/6] Fetching Google Cloud OAuth2 access token...")
    token = subprocess.check_output([GCLOUD, "auth", "print-access-token"]).decode().strip()
    return token

def make_request(url, method="GET", data=None, token=None, content_type="application/json"):
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Goog-User-Project": PROJECT_ID,
    }
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        print(f"Error on {method} {url}: {e.code} {e.read().decode('utf-8', errors='ignore')}")
        raise

def main():
    print("=" * 70)
    print("  Deploying CloudPort to Google Firebase Hosting (100% Free / No Billing)")
    print(f"  Project ID : {PROJECT_ID}")
    print(f"  Target URL : https://{SITE_ID}.web.app")
    print("=" * 70)

    token = get_access_token()

    # Step 1: Create a new Version
    print("\n[2/6] Creating new Firebase Hosting version...")
    ver_url = f"https://firebasehosting.googleapis.com/v1beta1/sites/{SITE_ID}/versions"
    ver_payload = json.dumps({
        "config": {
            "headers": [
                {
                    "glob": "**",
                    "headers": {
                        "Cache-Control": "max-age=1800"
                    }
                }
            ]
        }
    }).encode("utf-8")
    status, body = make_request(ver_url, method="POST", data=ver_payload, token=token)
    ver_data = json.loads(body.decode("utf-8"))
    version_name = ver_data["name"]
    version_id = version_name.split("/")[-1]
    print(f"      -> Version created: {version_id}")

    # Step 2: Gzip & Hash frontend files
    print("\n[3/6] Gzipping and computing SHA-256 hashes of frontend assets...")
    files_map = {}
    content_map = {}

    import gzip

    for root, dirs, files in os.walk(FRONTEND_DIR):
        for f in files:
            full_path = os.path.join(root, f)
            rel_path = "/" + os.path.relpath(full_path, FRONTEND_DIR).replace("\\", "/")
            with open(full_path, "rb") as fl:
                raw_data = fl.read()
            # Firebase Hosting requires gzipped bytes for upload
            gzipped_data = gzip.compress(raw_data, compresslevel=9)
            h = hashlib.sha256(gzipped_data).hexdigest()
            files_map[rel_path] = h
            content_map[h] = gzipped_data
            print(f"      -> {rel_path} ({len(raw_data)} -> {len(gzipped_data)} bytes gzipped, hash: {h[:12]}...)")

    # Step 3: Populate files
    print("\n[4/6] Registering file hashes with Firebase...")
    pop_url = f"https://firebasehosting.googleapis.com/v1beta1/sites/{SITE_ID}/versions/{version_id}:populateFiles"
    pop_payload = json.dumps({"files": files_map}).encode("utf-8")
    status, body = make_request(pop_url, method="POST", data=pop_payload, token=token)
    pop_data = json.loads(body.decode("utf-8"))
    upload_url = pop_data.get("uploadUrl", "")
    upload_required = pop_data.get("uploadRequiredHashes", [])
    print(f"      -> Required uploads: {len(upload_required)} of {len(files_map)} files")

    # Step 4: Upload missing files
    if upload_required and upload_url:
        print("\n[5/6] Uploading static files...")
        for h in upload_required:
            data = content_map[h]
            target_url = f"{upload_url}/{h}"
            status, _ = make_request(target_url, method="POST", data=data, token=token, content_type="application/octet-stream")
            print(f"      -> Uploaded hash {h[:12]}... (HTTP {status})")
    else:
        print("\n[5/6] All file hashes already cached on Google CDN.")

    # Step 5: Finalize version
    print("\n[6/6] Finalizing version and publishing live release...")
    fin_url = f"https://firebasehosting.googleapis.com/v1beta1/sites/{SITE_ID}/versions/{version_id}?update_mask=status"
    fin_payload = json.dumps({"status": "FINALIZED"}).encode("utf-8")
    make_request(fin_url, method="PATCH", data=fin_payload, token=token)

    # Step 6: Create release
    rel_url = f"https://firebasehosting.googleapis.com/v1beta1/sites/{SITE_ID}/releases?versionName={version_name}"
    make_request(rel_url, method="POST", data=b"", token=token)

    live_url = f"https://{SITE_ID}.web.app"
    live_alt = f"https://{SITE_ID}.firebaseapp.com"
    print("\n" + "=" * 70)
    print("  SUCCESSFULLY DEPLOYED TO GOOGLE HOSTING!")
    print(f"  Live Website URL : {live_url}")
    print(f"  Alternative URL  : {live_alt}")
    print("=" * 70)

if __name__ == "__main__":
    main()
