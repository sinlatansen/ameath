"""字体管理模块 - 支持 Zpix 像素字体"""

import tkinter.font as tkfont
from pathlib import Path


def _load_zpix_font():
    """从文件加载 Zpix 字体（Windows）"""
    try:
        import ctypes
        import os

        project_dir = Path(__file__).parent.parent
        font_path = project_dir / "fonts" / "zpix.ttf"

        if not font_path.exists():
            return False

        gdi32 = ctypes.windll.gdi32
        FR_PRIVATE = 0x10

        # 使用绝对路径
        abs_path = os.path.abspath(str(font_path))
        result = gdi32.AddFontResourceExW(abs_path, FR_PRIVATE, 0)

        if result > 0:
            # 发送 WM_FONTCHANGE 消息通知系统字体已更改
            # 使用 PostMessage 代替 SendMessage 避免阻塞主线程
            HWND_BROADCAST = 0xFFFF
            WM_FONTCHANGE = 0x001D
            ctypes.windll.user32.PostMessageW(HWND_BROADCAST, WM_FONTCHANGE, 0, 0)
            return True

    except Exception:
        pass

    return False


def _is_zpix_available():
    """检查 Zpix 字体是否可用"""
    try:
        available_fonts = tkfont.families()
        return "Zpix" in available_fonts
    except Exception:
        return False


def get_font_family():
    """获取可用的字体，优先使用 Zpix"""
    # 尝试从文件加载 Zpix
    if _load_zpix_font():
        if _is_zpix_available():
            return "Zpix"

    # 检查系统是否已安装 Zpix
    if _is_zpix_available():
        return "Zpix"

    # 回退到系统默认中文字体
    return "Microsoft YaHei UI"


def get_font_config():
    """获取字体配置"""
    font_family = get_font_family()

    if font_family == "Zpix":
        # Zpix 像素字体使用稍大的字号
        return {
            "family": font_family,
            "title": (font_family, 14, "bold"),
            "subtitle": (font_family, 12, "bold"),
            "base": (font_family, 12),
            "small": (font_family, 10),
            "control": (font_family, 12),
        }
    else:
        # 系统字体使用标准字号
        return {
            "family": font_family,
            "title": (font_family, 12, "bold"),
            "subtitle": (font_family, 11, "bold"),
            "base": (font_family, 10),
            "small": (font_family, 9),
            "control": (font_family, 11),
        }
