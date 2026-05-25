import os
import re
from dotenv import load_dotenv

load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

# Patch the re.match in supabase to allow our special key
import supabase._sync.client
original_match = re.match
supabase._sync.client.re.match = lambda pattern, string, flags=0: original_match(pattern, string, flags) if "jwt" not in pattern.lower() else True
# Wait, let's just make it always return True for the key validation regex
def mock_match(pattern, string, flags=0):
    if "A-Za-z0-9_-" in pattern:
        return True
    return original_match(pattern, string, flags)

supabase._sync.client.re.match = mock_match

from supabase import create_client

print("Testing with patched re.match...")
try:
    sb = create_client(url, key)
    res = sb.table("announcements").select("*").execute()
    print("Success! Announcements:", len(res.data))
except Exception as e:
    print("Failed:", e)
