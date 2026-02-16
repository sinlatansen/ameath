import json
import os
import sys

from .constants import (
    CONFIG_FILE,
    DEFAULT_SCALE_INDEX,
    DEFAULT_TRANSPARENCY_INDEX,
    DEFAULT_WANDER_IDLE_STAY_MODE,
    SCALE_OPTIONS,
    TRANSPARENCY_OPTIONS,
    DEFAULT_VOICE_ENABLED,
    DEFAULT_VOICE_VOLUME,
)


DEFAULT_CONFIG = {
    "scale_index": DEFAULT_SCALE_INDEX,
    "transparency_index": DEFAULT_TRANSPARENCY_INDEX,
    "auto_startup": True,
    "click_through": True,
    "follow_mouse": False,
    "display_priority": 1,
    "wander_idle_stay_mode": DEFAULT_WANDER_IDLE_STAY_MODE,
    "instance_count": 1,
    "skip_updates": False,
    "skip_version": None,
    "voice_enabled": DEFAULT_VOICE_ENABLED,  # 添加语音开关
    "voice_volume": DEFAULT_VOICE_VOLUME,    # 添加语音音量
    "music_enabled": True,                  # 默认开启音乐播放器
    "music_volume": 100,                   # 音乐音量默认100%
}

def _coerce_bool(value, default):
    if isinstance(value, bool):
        return value
    return default


def _coerce_int(value, default, min_value=None, max_value=None):
    try:
        value = int(value)
    except Exception:
        return default
    if min_value is not None and value < min_value:
        return default
    if max_value is not None and value > max_value:
        return default
    return value


def _sanitize_config(config):
    if not isinstance(config, dict):
        return DEFAULT_CONFIG.copy()

    result = DEFAULT_CONFIG.copy()
    result["scale_index"] = _coerce_int(
        config.get("scale_index"),
        DEFAULT_CONFIG["scale_index"],
        min_value=0,
        max_value=len(SCALE_OPTIONS) - 1,
    )
    result["transparency_index"] = _coerce_int(
        config.get("transparency_index"),
        DEFAULT_CONFIG["transparency_index"],
        min_value=0,
        max_value=len(TRANSPARENCY_OPTIONS) - 1,
    )
    result["auto_startup"] = _coerce_bool(
        config.get("auto_startup"), DEFAULT_CONFIG["auto_startup"]
    )
    result["click_through"] = _coerce_bool(
        config.get("click_through"), DEFAULT_CONFIG["click_through"]
    )
    result["follow_mouse"] = _coerce_bool(
        config.get("follow_mouse"), DEFAULT_CONFIG["follow_mouse"]
    )
    result["display_priority"] = _coerce_int(
        config.get("display_priority"),
        DEFAULT_CONFIG["display_priority"],
        min_value=1,
        max_value=3,
    )
    result["wander_idle_stay_mode"] = _coerce_int(
        config.get("wander_idle_stay_mode"),
        DEFAULT_CONFIG["wander_idle_stay_mode"],
        min_value=0,
        max_value=2,
    )
    result["instance_count"] = _coerce_int(
        config.get("instance_count"),
        DEFAULT_CONFIG["instance_count"],
        min_value=1,
    )
    result["skip_updates"] = _coerce_bool(
        config.get("skip_updates"), DEFAULT_CONFIG["skip_updates"]
    )
    result["skip_version"] = config.get("skip_version")
    result["voice_enabled"] = _coerce_bool(
        config.get("voice_enabled"), DEFAULT_CONFIG["voice_enabled"]
    )
    result["voice_volume"] = _coerce_int(
        config.get("voice_volume"),
        DEFAULT_CONFIG["voice_volume"],
        min_value=0,
        max_value=100,  # 修改为100%
    )
    result["music_enabled"] = _coerce_bool(
        config.get("music_enabled"), DEFAULT_CONFIG["music_enabled"]
    )
    result["music_volume"] = _coerce_int(
        config.get("music_volume"),
        DEFAULT_CONFIG["music_volume"],
        min_value=0,
        max_value=100,  # 100%
    )
    return result


def load_config():
    """加载配置"""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            return _sanitize_config(config)
    except Exception:
        return DEFAULT_CONFIG.copy()


def save_config(config):
    """保存配置"""
    config_dir = os.path.dirname(CONFIG_FILE)
    if config_dir and not os.path.exists(config_dir):
        os.makedirs(config_dir, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_startup_executable_path():
    """获取注册表中保存的exe路径（如果有）"""
    key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    value_name = "DesktopPet"
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_READ
        ) as reg_key:
            return winreg.QueryValueEx(reg_key, value_name)[0]
    except Exception:
        return None


def set_auto_startup(enable):
    """设置开机自启"""
    key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    value_name = "DesktopPet"

    # 检测程序是否打包成exe
    if getattr(sys, "frozen", False):
        # 打包后的exe，使用exe本身路径
        executable_path = sys.executable
        startup_cmd = f'"{executable_path}"'
    else:
        # 开发的py文件，使用pythonw启动
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Python\PythonCore\3.*\InstallPath",
                0,
                winreg.KEY_READ,
            ) as reg_key:
                python_path, _ = winreg.QueryValueEx(reg_key, "InstallPath")
                executable_path = os.path.join(python_path, "pythonw.exe")
        except Exception:
            executable_path = "pythonw"
        startup_cmd = f'{executable_path} "{os.path.abspath(sys.argv[0])}"'

    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_ALL_ACCESS
        ) as reg_key:
            if enable:
                winreg.SetValueEx(reg_key, value_name, 0, winreg.REG_SZ, startup_cmd)
            else:
                try:
                    winreg.DeleteValue(reg_key, value_name)
                except FileNotFoundError:
                    pass
    except Exception as e:
        print(f"设置开机自启失败: {e}")


def check_and_fix_startup():
    """检查开机自启路径是否正确（exe移动后自动修复"""
    if not getattr(sys, "frozen", False):
        return  # 只处理打包后的exe

    saved_path = get_startup_executable_path()
    current_path = f'"{sys.executable}"'

    # 如果注册表有记录但路径不一致，说明用户移动了exe，自动更新
    if saved_path and saved_path != current_path:
        print("检测到exe位置已变更，自动更新开机自启...")
        set_auto_startup(True)
