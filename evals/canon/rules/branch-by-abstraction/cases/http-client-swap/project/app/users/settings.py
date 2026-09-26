"""User settings."""
from app import httpclient


def save_settings(user_id, values):
    return httpclient.post_json(f"/users/{user_id}/settings", values)
