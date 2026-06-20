"""
config_loader.py - 从 public_config.yaml 加载配置
所有模块统一通过此模块读取配置
"""

import yaml
import os

CONFIG_FILE = "public_config.yaml"

_config_cache = None


def load_config():
    """加载公共配置（带缓存）"""
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"找不到配置文件: {CONFIG_FILE}")

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        _config_cache = yaml.safe_load(f)
    return _config_cache


def get(key_path, default=None):
    """
    按点分路径获取配置值。
    例如: get('comfyui.server') -> 'http://127.0.0.1:8188'
    """
    cfg = load_config()
    parts = key_path.split(".")
    val = cfg
    for p in parts:
        if isinstance(val, dict) and p in val:
            val = val[p]
        else:
            return default
    return val
