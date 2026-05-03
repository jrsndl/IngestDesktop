import urllib.request
import json
import sys

token = "YOUR_GITHUB_PAT"
repo_name = "IngestDesktop"

url = "https://api.github.com/user/repos"
data = json.dumps({"name": repo_name, "private": False}).encode('utf-8')

req = urllib.request.Request(url, data=data)
req.add_header("Authorization", f"token {token}")
req.add_header("Accept", "application/vnd.github.v3+json")
req.add_header("Content-Type", "application/json")

try:
    with urllib.request.urlopen(req) as response:
        res = json.loads(response.read().decode())
        print(f"SUCCESS: {res['clone_url']}")
except urllib.error.HTTPError as e:
    print(f"ERROR: {e.code} - {e.read().decode()}")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: {str(e)}")
    sys.exit(1)
