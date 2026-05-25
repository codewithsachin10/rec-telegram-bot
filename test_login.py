import os
from dotenv import load_dotenv

load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

# Patch supabase-py to allow non-JWT 'sb_publishable' keys
import supabase._sync.client
import re
_original_match = re.match
def _mock_match(pattern, string, flags=0):
    if string == key and "sb_" in string:
        return True
    return _original_match(pattern, string, flags)
supabase._sync.client.re.match = _mock_match

from supabase import create_client
supabase = create_client(url, key)

email = "sachin.g.2025.csbs@rajalakshmi.edu.in"
password = "Changeme@123"

try:
    print(f"Attempting login for {email}...")
    auth_response = supabase.auth.sign_in_with_password({"email": email, "password": password})
    print("Success! User ID:", auth_response.user.id)
except Exception as e:
    print("Login Failed:", e)
