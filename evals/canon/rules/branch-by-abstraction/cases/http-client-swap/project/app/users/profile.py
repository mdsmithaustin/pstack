"""User profiles."""
from app import httpclient


def fetch_profile(user_id):
    return httpclient.get_json(f"/users/{user_id}")
