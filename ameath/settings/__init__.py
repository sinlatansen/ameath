"""设置模块 - 提供设置窗口及相关功能

使用方式:
    from ameath.settings import SettingsWindow, show_settings_dialog
"""

# 从 base.py 导入（包含所有模块化的设置窗口组件）
from .base import SettingsWindow, show_settings_dialog

__all__ = ["SettingsWindow", "show_settings_dialog"]
