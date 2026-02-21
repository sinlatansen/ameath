"""设置窗口模块 - 包含个性化、检查更新、关于三个标签页"""

import os
import tkinter as tk
import getpass
from tkinter import messagebox
from tkinter import ttk
import webbrowser
import threading

from PIL import Image, ImageTk

from ..config import load_config, save_config, set_auto_startup
from ..fonts import get_font_config
from ..constants import (
    SCREEN_INDEX,
    SCALE_OPTIONS,
    TRANSPARENCY_OPTIONS,
    GITEE_RELEASES_URL,
    DEFAULT_SCREEN_INDEX,
    DEFAULT_SCALE_INDEX,
    DEFAULT_TRANSPARENCY_INDEX,
    DEFAULT_WANDER_IDLE_STAY_MODE,
    DEFAULT_VOICE_ENABLED,
    DEFAULT_VOICE_VOLUME,
)
from ..utils import resource_path, check_update, download_and_update, get_git_hash

# Import tab creation methods from separate modules
from .personalization import create_personalization_tab
from .update import create_update_tab
from .about import create_about_tab
from .music import create_music_tab, MusicPlayerEmbedded


class SettingsWindow:
    """设置窗口类"""

    def __init__(self, parent, app, version):
        self.parent = parent
        self.app = app
        self.version = version
        self.git_hash = get_git_hash()
        self.window = None
        self._update_check_thread = None
        self.notebook = None
        self.update_frame = None
        self.latest_version = None
        self._latest_asset_url = None
        self._latest_asset_name = None
        self._download_thread = None
        self._restore_display_priority = None
        self._pets_paused_by_settings = False
        self.colors = {
            "bg": "#FFF1F6",
            "card_bg": "#FFFFFF",
            "border": "#F3C2D4",
            "accent": "#FF69B4",
            "accent_dark": "#E84D8E",
            "text": "#4A2A3A",
            "subtext": "#7A5564",
            "tab_bg": "#FFE1EE",
            "tab_active": "#FFD1E5",
        }
        font_config = get_font_config()
        self.font_family = font_config["family"]
        self.fonts = {
            "title": font_config["title"],
            "subtitle": font_config["subtitle"],
            "base": font_config["base"],
            "small": font_config["small"],
            "control": font_config["control"],
        }

    def _configure_theme(self):
        style = ttk.Style(self.window)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background=self.colors["bg"])
        style.configure(
            "TLabel",
            background=self.colors["bg"],
            foreground=self.colors["text"],
            font=self.fonts["base"],
        )
        style.configure("TNotebook", background=self.colors["bg"], borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=self.colors["tab_bg"],
            foreground=self.colors["text"],
            padding=(12, 5),
            font=self.fonts["base"],
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", self.colors["tab_active"])],
            foreground=[("selected", self.colors["accent_dark"])],
            padding=[("selected", (18, 8))],
            font=[("selected", self.fonts["subtitle"])],
        )
        style.configure("TSeparator", background=self.colors["border"])

    def _create_window(self):
        """创建设置窗口（内部方法）"""
        # 临时显示父窗口以确保 Toplevel 能正常创建
        parent_was_hidden = False
        try:
            parent_was_hidden = not self.parent.winfo_viewable()
        except Exception:
            pass

        if parent_was_hidden:
            self.parent.deiconify()

        self.window = tk.Toplevel(self.parent)

        # 父窗口可以再次隐藏（设置窗口已独立，不受影响）
        if parent_was_hidden:
            self.parent.withdraw()
        self.window.title("设置")
        # 窗口尺寸: 1000x1000（自适应屏幕）
        self.window.update_idletasks()
        screen_w = self.window.winfo_screenwidth()
        screen_h = self.window.winfo_screenheight()
        window_w = min(1000, max(600, screen_w - 80))
        window_h = min(1000, max(600, screen_h - 80))
        self.window.geometry(f"{window_w}x{window_h}")
        self.window.minsize(min(900, window_w), min(900, window_h))
        self.window.resizable(True, True)
        self.window.attributes("-topmost", True)
        # 注意：不使用 transient，否则父窗口隐藏时设置窗口也会消失
        # self.window.transient(self.parent)
        self.window.configure(bg=self.colors["bg"])
        self._configure_theme()

        if getattr(self.app, "display_priority", None) == 3:
            self._restore_display_priority = 3
            self.app.set_display_priority(1, persist=False)

        # 设置窗口图标
        try:
            icon_path = resource_path("gifs/ameath.ico")
            if os.path.exists(icon_path):
                self.window.iconbitmap(icon_path)
        except Exception:
            pass

        # 居中显示
        x = max((screen_w - window_w) // 2, 0)
        y = max((screen_h - window_h) // 2, 0)
        self.window.geometry(f"{window_w}x{window_h}+{x}+{y}")

        # 创建主容器
        main_frame = tk.Frame(self.window, bg=self.colors["bg"])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)

        # 创建标签页
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # 个性化标签页
        self.personalization_frame = create_personalization_tab(self, self.notebook)
        self.notebook.add(self.personalization_frame, text="个性化")

        # 音乐播放器标签页
        self.music_frame = create_music_tab(self, self.notebook)
        self.notebook.add(self.music_frame, text="音乐")

        # 检查更新标签页
        self.update_frame = create_update_tab(self, self.notebook)
        self.notebook.add(self.update_frame, text="检查更新")

        # 关于标签页
        self.about_frame = create_about_tab(self, self.notebook)
        self.notebook.add(self.about_frame, text="关于")

        # 关闭按钮区域
        btn_frame = tk.Frame(main_frame, bg=self.colors["bg"])
        btn_frame.pack(fill=tk.X, pady=(15, 0))

        tk.Button(
            btn_frame,
            text="确定",
            command=self._on_close,
            width=12,
            font=self.fonts["base"],
            bg=self.colors["accent"],
            fg="white",
            activebackground=self.colors["accent_dark"],
            activeforeground="white",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
        ).pack(side=tk.RIGHT)

        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        return main_frame

    def show(self):
        """显示设置窗口（默认显示个性化标签页）"""
        if self.window is not None and self.window.winfo_exists():
            self.window.lift()
            self.window.focus_force()
            return

        # 检查实例数，如果大于10则暂停所有桌宠以保证设置窗口流畅
        self._check_and_pause_pets()

        self._create_window()
        self.window.focus_force()

    def show_with_music_tab(self):
        """显示设置窗口并切换到音乐播放器标签页"""
        if self.window is not None and self.window.winfo_exists():
            # 窗口已存在，切换到音乐标签页
            self.notebook.select(self.music_frame)
            self.window.lift()
            self.window.focus_force()
            return

        # 检查实例数，如果大于10则暂停所有桌宠以保证设置窗口流畅
        self._check_and_pause_pets()

        self._create_window()
        # 切换到音乐标签页
        self.notebook.select(self.music_frame)
        self.window.focus_force()

    def show_with_update_tab(self, auto_check=True):
        """显示设置窗口并切换到检查更新标签页

        Args:
            auto_check: 是否自动触发更新检查（默认True）
        """
        if self.window is not None and self.window.winfo_exists():
            # 窗口已存在，切换到更新标签页
            self.notebook.select(self.update_frame)
            self.window.lift()
            self.window.focus_force()
            if auto_check:
                self.window.after(500, self._on_check_update)  # 延迟触发检查
            return

        # 检查实例数，如果大于10则暂停所有桌宠以保证设置窗口流畅
        self._check_and_pause_pets()

        self._create_window()
        # 切换到检查更新标签页（索引1）
        self.notebook.select(self.update_frame)
        self.window.focus_force()

        # 自动触发更新检查（延迟500ms确保窗口已显示）
        if auto_check:
            self.window.after(600, self._on_check_update)

    def _on_close(self):
        """关闭窗口"""
        if self._restore_display_priority is not None:
            if getattr(self, "display_priority_var", None) is not None:
                if self.display_priority_var.get() == self._restore_display_priority:
                    self.app.set_display_priority(
                        self._restore_display_priority, persist=False
                    )
            self._restore_display_priority = None

        # 恢复被暂停的桌宠
        self._restore_pets_if_paused()

        if self.window:
            self.window.destroy()
            self.window = None

    def _check_and_pause_pets(self):
        """检查实例数，如果大于10则暂停所有桌宠以保证设置窗口流畅"""
        try:
            if hasattr(self.app, "pets") and len(self.app.pets) > 10:
                # 只有在未暂停的情况下才暂停
                if not self.app.is_paused:
                    self.app.toggle_pause()
                    self._pets_paused_by_settings = True
        except Exception as e:
            print(f"设置窗口：暂停桌宠时出错: {e}")

    def _restore_pets_if_paused(self):
        """如果之前被设置窗口暂停，则恢复桌宠运行"""
        try:
            if self._pets_paused_by_settings and self.app.is_paused:
                self.app.toggle_pause()
                self._pets_paused_by_settings = False
        except Exception as e:
            print(f"设置窗口：恢复桌宠时出错: {e}")


# ===== Setup callbacks for all tabs =====

from .personalization import setup_personalization_callbacks
from .update import setup_update_callbacks

# Setup all callbacks
setup_personalization_callbacks(SettingsWindow)
setup_update_callbacks(SettingsWindow)


# ===== Convenience function =====


def show_settings_dialog(parent, app, version, open_music_tab=False):
    """显示设置对话框的便捷函数

    Args:
        parent: 父窗口
        app: 应用实例
        version: 版本号
        open_music_tab: 是否直接打开音乐标签页（默认False）
    """
    settings = SettingsWindow(parent, app, version)
    if open_music_tab:
        settings.show_with_music_tab()
    else:
        settings.show()
