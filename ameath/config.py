import json
import os
import sys

from .constants import CONFIG_FILE, DEFAULT_SCALE_INDEX, DEFAULT_TRANSPARENCY_INDEX


def load_config():
    """加载配置"""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "scale_index": DEFAULT_SCALE_INDEX,
            "transparency_index": DEFAULT_TRANSPARENCY_INDEX,
            "auto_startup": False,
            "click_through": True,
            "follow_mouse": False,
        }


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
    """检查开机自启路径是否正确（exe移动后自动修复）"""
    if not getattr(sys, "frozen", False):
        return  # 只处理打包后的exe

    saved_path = get_startup_executable_path()
    current_path = f'"{sys.executable}"'

    # 如果注册表有记录但路径不一致，说明用户移动了exe，自动更新
    if saved_path and saved_path != current_path:
        print("检测到exe位置已变更，自动更新开机自启...")
        set_auto_startup(True)
