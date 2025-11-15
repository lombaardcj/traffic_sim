import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')


def load_config():
    """Load configuration from config.json. Returns None if missing or unreadable."""
    if not os.path.exists(CONFIG_PATH):
        print(f"Config file not found at {CONFIG_PATH}")
        return None
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Failed to read config file: {e}")
        return None


def save_config(cfg):
    """Write the provided config object back to disk."""
    try:
        with open(CONFIG_PATH, 'w') as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"Failed to save config: {e}")


# Load on import (caller can check for None and decide how to proceed)
config = load_config()
