"""配置管理 - 持久化存储应用设置。"""

import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.json")

DEFAULT_CONFIG = {
    "home_lat": None,
    "home_lon": None,
    "home_address": "",
    "emergency_contacts": [],
    "max_distance_meters": 500,
    "max_time_minutes": 60,
    "preset_routes": [],
    "voice_enabled": True,
    "alert_enabled": True,
    "first_launch": True,
}


def load_config():
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key, val in DEFAULT_CONFIG.items():
            if key not in data:
                data[key] = val
        return data
    except (json.JSONDecodeError, IOError):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()


def save_config(config):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def update_config(key, value):
    cfg = load_config()
    cfg[key] = value
    save_config(cfg)
    return cfg
