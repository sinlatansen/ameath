"""设置窗口模块 - 包含个性化、检查更新、关于三个标签页"""

import tkinter as tk
import getpass
from tkinter import messagebox
from tkinter import ttk
import webbrowser
import threading

from PIL import Image, ImageTk

from .config import load_config, save_config, set_auto_startup
from .constants import (
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
from .utils import resource_path, check_update, download_and_update, get_git_hash


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
        self.fonts = {
            "title": ("Microsoft YaHei UI", 12, "bold"),
            "subtitle": ("Microsoft YaHei UI", 11, "bold"),
            "base": ("Microsoft YaHei UI", 10),
            "small": ("Microsoft YaHei UI", 9),
            "control": ("Microsoft YaHei UI", 11),
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
        self.window = tk.Toplevel(self.parent)
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
        self.window.transient(self.parent)
        self.window.configure(bg=self.colors["bg"])
        self._configure_theme()

        if getattr(self.app, "display_priority", None) == 3:
            self._restore_display_priority = 3
            self.app.set_display_priority(1, persist=False)

        # 设置窗口图标
        try:
            icon_image = Image.open(resource_path("gifs/ameath.gif"))
            icon_image = icon_image.resize((64, 64), Image.Resampling.LANCZOS)
            icon_pil = icon_image.convert("RGBA")
            app_icon = ImageTk.PhotoImage(icon_pil)
            self.window.iconphoto(True, app_icon)
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
        self.personalization_frame = self._create_personalization_tab(self.notebook)
        self.notebook.add(self.personalization_frame, text="个性化")

        # 音乐播放器标签页
        self.music_frame = self._create_music_tab(self.notebook)
        self.notebook.add(self.music_frame, text="音乐")

        # 检查更新标签页
        self.update_frame = self._create_update_tab(self.notebook)
        self.notebook.add(self.update_frame, text="检查更新")

        # 关于标签页
        self.about_frame = self._create_about_tab(self.notebook)
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

    def _create_personalization_tab(self, parent):
        """创建个性化标签页"""
        frame = ttk.Frame(parent)
        canvas = tk.Canvas(
            frame,
            bg=self.colors["bg"],
            highlightthickness=0,
            bd=0,
        )
        scrollbar = tk.Scrollbar(
            frame,
            orient=tk.VERTICAL,
            command=canvas.yview,
            width=12,
            bg=self.colors["tab_bg"],
            activebackground=self.colors["tab_active"],
            troughcolor=self.colors["card_bg"],
        )
        canvas.configure(yscrollcommand=scrollbar.set)

        content = tk.Frame(canvas, bg=self.colors["bg"])
        inner_frame = tk.Frame(content, bg=self.colors["bg"])
        inner_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        canvas_window = canvas.create_window((0, 0), window=content, anchor="nw")

        def _on_content_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfigure(canvas_window, width=event.width)

        def _on_mousewheel(event):
            if event.delta:
                canvas.yview_scroll(-1 * int(event.delta / 120), "units")

        def _bind_mousewheel(_event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_mousewheel(_event):
            canvas.unbind_all("<MouseWheel>")

        content.bind("<Configure>", _on_content_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.bind("<Enter>", _bind_mousewheel)
        canvas.bind("<Leave>", _unbind_mousewheel)
        content.bind("<Enter>", _bind_mousewheel)
        content.bind("<Leave>", _unbind_mousewheel)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 加载当前配置
        config = load_config()
        current_total_screen = config.get("total_screen", True)
        current_screen_idx = config.get("screen_index", DEFAULT_SCREEN_INDEX)
        current_scale_idx = config.get("scale_index", DEFAULT_SCALE_INDEX)
        current_transparency_idx = config.get(
            "transparency_index", DEFAULT_TRANSPARENCY_INDEX
        )
        current_auto_startup = config.get("auto_startup", False)
        current_display_priority = config.get("display_priority", 1)
        current_wander_idle_stay_mode = config.get(
            "wander_idle_stay_mode", DEFAULT_WANDER_IDLE_STAY_MODE
        )
        current_instance_count = config.get("instance_count", 1)
        current_voice_enabled = config.get("voice_enabled", DEFAULT_VOICE_ENABLED)
        current_voice_volume = config.get("voice_volume", DEFAULT_VOICE_VOLUME)

        # ===== 缩放设置 =====
        scale_frame = tk.LabelFrame(
            inner_frame,
            text="缩放比例",
            font=self.fonts["subtitle"],
            padx=15,
            pady=12,
            bg=self.colors["card_bg"],
            fg=self.colors["accent_dark"],
            bd=1,
            relief=tk.SOLID,
        )
        scale_frame.pack(fill=tk.X, pady=(0, 15), ipady=5)

        self.scale_var = tk.IntVar(value=current_scale_idx)

        # 使用网格布局，多列展示
        scale_grid = tk.Frame(scale_frame, bg=self.colors["card_bg"])
        scale_grid.pack(fill=tk.X, pady=5)

        scale_columns = 5
        for i, scale_val in enumerate(SCALE_OPTIONS):
            row = i // scale_columns
            col = i % scale_columns
            rb = tk.Radiobutton(
                scale_grid,
                text=f"{scale_val}x",
                variable=self.scale_var,
                value=i,
                font=self.fonts["control"],
                bg=self.colors["card_bg"],
                fg=self.colors["text"],
                activebackground=self.colors["card_bg"],
                activeforeground=self.colors["accent_dark"],
                selectcolor=self.colors["bg"],
                command=self._on_scale_changed,
                anchor=tk.W,
            )
            rb.grid(row=row, column=col, sticky=tk.W, padx=15, pady=6)

        # ===== 透明度设置 =====
        trans_frame = tk.LabelFrame(
            inner_frame,
            text="窗口透明度",
            font=self.fonts["subtitle"],
            padx=15,
            pady=12,
            bg=self.colors["card_bg"],
            fg=self.colors["accent_dark"],
            bd=1,
            relief=tk.SOLID,
        )
        trans_frame.pack(fill=tk.X, pady=(0, 15), ipady=5)

        self.transparency_var = tk.IntVar(value=current_transparency_idx)

        # 使用网格布局，多列展示
        trans_grid = tk.Frame(trans_frame, bg=self.colors["card_bg"])
        trans_grid.pack(fill=tk.X, pady=5)

        trans_columns = 5
        for i, trans_val in enumerate(TRANSPARENCY_OPTIONS):
            row = i // trans_columns
            col = i % trans_columns
            rb = tk.Radiobutton(
                trans_grid,
                text=f"{int(trans_val * 100)}%",
                variable=self.transparency_var,
                value=i,
                font=self.fonts["control"],
                bg=self.colors["card_bg"],
                fg=self.colors["text"],
                activebackground=self.colors["card_bg"],
                activeforeground=self.colors["accent_dark"],
                selectcolor=self.colors["bg"],
                command=self._on_transparency_changed,
                anchor=tk.W,
            )
            rb.grid(row=row, column=col, sticky=tk.W, padx=20, pady=6)

        # ===== 开机自启设置 =====
        startup_frame = tk.LabelFrame(
            inner_frame,
            text="启动选项",
            font=self.fonts["subtitle"],
            padx=15,
            pady=12,
            bg=self.colors["card_bg"],
            fg=self.colors["accent_dark"],
            bd=1,
            relief=tk.SOLID,
        )
        startup_frame.pack(fill=tk.X, pady=(0, 10), ipady=5)

        self.auto_startup_var = tk.BooleanVar(value=current_auto_startup)
        startup_cb = tk.Checkbutton(
            startup_frame,
            text="开机时自动启动程序",
            variable=self.auto_startup_var,
            font=self.fonts["control"],
            bg=self.colors["card_bg"],
            fg=self.colors["text"],
            activebackground=self.colors["card_bg"],
            activeforeground=self.colors["accent_dark"],
            selectcolor=self.colors["bg"],
            command=self._on_startup_changed,
            anchor=tk.W,
        )
        startup_cb.pack(anchor=tk.W, pady=3)

        # 添加说明文字
        tk.Label(
            startup_frame,
            text="开启后，系统启动时将自动运行桌面宠物",
            font=self.fonts["small"],
            fg=self.colors["subtext"],
            bg=self.colors["card_bg"],
            anchor=tk.W,
        ).pack(anchor=tk.W, padx=22)

        # ===== 语音设置 =====
        voice_frame = tk.LabelFrame(
            inner_frame,
            text="语音设置",
            font=self.fonts["subtitle"],
            padx=15,
            pady=12,
            bg=self.colors["card_bg"],
            fg=self.colors["accent_dark"],
            bd=1,
            relief=tk.SOLID,
        )
        voice_frame.pack(fill=tk.X, pady=(0, 10), ipady=5)

        # 语音开关
        self.voice_enabled_var = tk.BooleanVar(value=current_voice_enabled)
        voice_enabled_cb = tk.Checkbutton(
            voice_frame,
            text="启用点击音效",
            variable=self.voice_enabled_var,
            font=self.fonts["control"],
            bg=self.colors["card_bg"],
            fg=self.colors["text"],
            activebackground=self.colors["card_bg"],
            activeforeground=self.colors["accent_dark"],
            selectcolor=self.colors["bg"],
            command=self._on_voice_enabled_changed,
            anchor=tk.W,
        )
        voice_enabled_cb.pack(anchor=tk.W, pady=3)

        # 音量滑块
        volume_row = tk.Frame(voice_frame, bg=self.colors["card_bg"])
        volume_row.pack(fill=tk.X, pady=(8, 3), padx=22)

        tk.Label(
            volume_row,
            text="音量: ",
            font=self.fonts["control"],
            bg=self.colors["card_bg"],
            fg=self.colors["text"],
        ).pack(side=tk.LEFT)

        self.voice_volume_var = tk.IntVar(value=current_voice_volume)
        self.voice_volume_scale = tk.Scale(
            volume_row,
            from_=0,
            to=150,
            orient=tk.HORIZONTAL,
            variable=self.voice_volume_var,
            length=200,
            font=self.fonts["small"],
            bg=self.colors["card_bg"],
            fg=self.colors["text"],
            highlightthickness=0,
            troughcolor=self.colors["tab_bg"],
            activebackground=self.colors["accent"],
            command=self._on_voice_volume_changed,
        )
        self.voice_volume_scale.pack(side=tk.LEFT, padx=(5, 10))

        self.voice_volume_label = tk.Label(
            volume_row,
            text=f"{current_voice_volume}%",
            font=self.fonts["control"],
            bg=self.colors["card_bg"],
            fg=self.colors["accent_dark"],
            width=5,
        )
        self.voice_volume_label.pack(side=tk.LEFT)

        # 说明文字
        tk.Label(
            voice_frame,
            text="拖动桌宠时播放随机音效，音量可随时调整",
            font=self.fonts["small"],
            fg=self.colors["subtext"],
            bg=self.colors["card_bg"],
            anchor=tk.W,
        ).pack(anchor=tk.W, padx=22)

        # ===== 音乐播放器设置 =====
        music_frame = tk.LabelFrame(
            inner_frame,
            text="音乐播放器",
            font=self.fonts["subtitle"],
            padx=15,
            pady=12,
            bg=self.colors["card_bg"],
            fg=self.colors["accent_dark"],
            bd=1,
            relief=tk.SOLID,
        )
        music_frame.pack(fill=tk.X, pady=(0, 10), ipady=5)

        # 音乐播放器开关
        self.music_enabled_var = tk.BooleanVar(value=config.get("music_enabled", False))
        music_enabled_cb = tk.Checkbutton(
            music_frame,
            text="启用右键音乐播放器",
            variable=self.music_enabled_var,
            font=self.fonts["control"],
            bg=self.colors["card_bg"],
            fg=self.colors["text"],
            activebackground=self.colors["card_bg"],
            activeforeground=self.colors["accent_dark"],
            selectcolor=self.colors["bg"],
            command=self._on_music_enabled_changed,
            anchor=tk.W,
        )
        music_enabled_cb.pack(anchor=tk.W, pady=3)

        # 音乐音量滑块
        music_volume_row = tk.Frame(music_frame, bg=self.colors["card_bg"])
        music_volume_row.pack(fill=tk.X, pady=(8, 3), padx=22)

        tk.Label(
            music_volume_row,
            text="音乐音量: ",
            font=self.fonts["control"],
            bg=self.colors["card_bg"],
            fg=self.colors["text"],
        ).pack(side=tk.LEFT)

        self.music_volume_var = tk.IntVar(value=config.get("music_volume", 100))
        self.music_volume_scale = tk.Scale(
            music_volume_row,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            variable=self.music_volume_var,
            length=200,
            font=self.fonts["small"],
            bg=self.colors["card_bg"],
            fg=self.colors["text"],
            highlightthickness=0,
            troughcolor=self.colors["tab_bg"],
            activebackground=self.colors["accent"],
            command=self._on_music_volume_changed,
        )
        self.music_volume_scale.pack(side=tk.LEFT, padx=(5, 10))

        self.music_volume_label = tk.Label(
            music_volume_row,
            text=f"{config.get('music_volume', 100)}%",
            font=self.fonts["control"],
            bg=self.colors["card_bg"],
            fg=self.colors["accent_dark"],
            width=5,
        )
        self.music_volume_label.pack(side=tk.LEFT)

        # 说明文字
        tk.Label(
            music_frame,
            text="右键点击桌宠打开音乐播放器",
            font=self.fonts["small"],
            fg=self.colors["subtext"],
            bg=self.colors["card_bg"],
            anchor=tk.W,
        ).pack(anchor=tk.W, padx=22)

        # ===== 屏幕设置 =====
        screen_frame = tk.LabelFrame(
            inner_frame,
            text="屏幕设置",
            font=self.fonts["subtitle"],
            padx=15,
            pady=12,
            bg=self.colors["card_bg"],
            fg=self.colors["accent_dark"],
            bd=1,
            relief=tk.SOLID,
        )
        screen_frame.pack(fill=tk.X, pady=(0, 10), ipady=5)

        tk.Label(
            screen_frame,
            text="提示：更改后需重启软件生效",
            font=self.fonts["small"],
            fg=self.colors["subtext"],
            bg=self.colors["card_bg"],
            anchor=tk.W,
        ).pack(anchor=tk.W, padx=2, pady=(6, 10))

        # 模式选择：固定屏幕 / 跨屏游荡
        self.display_mode_var = tk.StringVar(
            value="wander" if current_total_screen else "fixed"
        )

        # 固定屏幕选项（包含屏幕选择器）
        fixed_frame = tk.Frame(screen_frame, bg=self.colors["card_bg"])
        fixed_frame.pack(fill=tk.X, pady=(0, 5))

        fixed_rb = tk.Radiobutton(
            fixed_frame,
            text="固定屏幕",
            variable=self.display_mode_var,
            value="fixed",
            font=self.fonts["control"],
            bg=self.colors["card_bg"],
            fg=self.colors["text"],
            activebackground=self.colors["card_bg"],
            activeforeground=self.colors["accent_dark"],
            selectcolor=self.colors["bg"],
            command=self._on_display_mode_changed,
            anchor=tk.W,
        )
        fixed_rb.pack(side=tk.LEFT)

        # 屏幕选择器（紧随RadioButton之后）
        self.screen_select_container = tk.Frame(fixed_frame, bg=self.colors["card_bg"])
        self.screen_select_container.pack(side=tk.LEFT, padx=(10, 0))

        # 屏幕选项
        self.screen_var = tk.IntVar(value=current_screen_idx)
        screen_grid = tk.Frame(self.screen_select_container, bg=self.colors["card_bg"])
        screen_grid.pack(fill=tk.X)

        screen_columns = 5
        for i, screen_val in enumerate(SCREEN_INDEX):
            row = i // screen_columns
            col = i % screen_columns
            rb = tk.Radiobutton(
                screen_grid,
                text=f"屏幕{int(screen_val) + 1}",
                variable=self.screen_var,
                value=i,
                font=self.fonts["base"],
                bg=self.colors["card_bg"],
                fg=self.colors["text"],
                activebackground=self.colors["card_bg"],
                activeforeground=self.colors["accent_dark"],
                selectcolor=self.colors["bg"],
                command=self._on_screen_changed,
                anchor=tk.W,
            )
            rb.grid(row=row, column=col, sticky=tk.W, padx=10, pady=3)

        # 跨屏游荡选项
        wander_frame = tk.Frame(screen_frame, bg=self.colors["card_bg"])
        wander_frame.pack(fill=tk.X, pady=(10, 0))

        wander_rb = tk.Radiobutton(
            wander_frame,
            text="跨屏游荡",
            variable=self.display_mode_var,
            value="wander",
            font=self.fonts["control"],
            bg=self.colors["card_bg"],
            fg=self.colors["text"],
            activebackground=self.colors["card_bg"],
            activeforeground=self.colors["accent_dark"],
            selectcolor=self.colors["bg"],
            command=self._on_display_mode_changed,
            anchor=tk.W,
        )
        wander_rb.pack(side=tk.LEFT)

        # 提示文字
        tk.Label(
            wander_frame,
            text="（在多个屏幕间自由移动，强烈建议开启鼠标跟随）",
            font=self.fonts["small"],
            fg=self.colors["subtext"],
            bg=self.colors["card_bg"],
            anchor=tk.W,
        ).pack(side=tk.LEFT, padx=(5, 0))

        # 根据当前模式更新UI状态
        self._update_screen_options_visibility()

        # ===== 显示优先级设置 =====
        priority_frame = tk.LabelFrame(
            inner_frame,
            text="显示优先级",
            font=self.fonts["subtitle"],
            padx=15,
            pady=12,
            bg=self.colors["card_bg"],
            fg=self.colors["accent_dark"],
            bd=1,
            relief=tk.SOLID,
        )
        priority_frame.pack(fill=tk.X, pady=(0, 10), ipady=5)

        self.display_priority_var = tk.IntVar(value=current_display_priority)
        priority_options = [
            ("始终置顶", 1),
            ("全屏时隐藏", 2),
            ("仅在桌面显示", 3),
        ]
        for text, value in priority_options:
            rb = tk.Radiobutton(
                priority_frame,
                text=text,
                variable=self.display_priority_var,
                value=value,
                font=self.fonts["control"],
                bg=self.colors["card_bg"],
                fg=self.colors["text"],
                activebackground=self.colors["card_bg"],
                activeforeground=self.colors["accent_dark"],
                selectcolor=self.colors["bg"],
                command=self._on_display_priority_changed,
                anchor=tk.W,
            )
            rb.pack(anchor=tk.W, pady=2)

        tk.Label(
            priority_frame,
            text="仅在桌面显示：打开应用窗口时会被覆盖",
            font=self.fonts["small"],
            fg=self.colors["subtext"],
            bg=self.colors["card_bg"],
            anchor=tk.W,
        ).pack(anchor=tk.W, padx=22, pady=(6, 0))

        # ===== 多开模式 =====
        multi_frame = tk.LabelFrame(
            inner_frame,
            text="多开模式",
            font=self.fonts["subtitle"],
            padx=15,
            pady=12,
            bg=self.colors["card_bg"],
            fg=self.colors["accent_dark"],
            bd=1,
            relief=tk.SOLID,
        )
        multi_frame.pack(fill=tk.X, pady=(0, 10), ipady=5)

        multi_row = tk.Frame(multi_frame, bg=self.colors["card_bg"])
        multi_row.pack(anchor=tk.W, pady=4)

        tk.Label(
            multi_row,
            text="实例数量:",
            font=self.fonts["control"],
            bg=self.colors["card_bg"],
            fg=self.colors["text"],
        ).pack(side=tk.LEFT)

        self.instance_count_var = tk.StringVar(value=str(current_instance_count))
        self.instance_count_entry = tk.Entry(
            multi_row,
            textvariable=self.instance_count_var,
            width=6,
            font=self.fonts["control"],
            bg=self.colors["bg"],
            fg=self.colors["text"],
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=self.colors["border"],
            highlightcolor=self.colors["accent"],
        )
        self.instance_count_entry.pack(side=tk.LEFT, padx=(8, 8))

        tk.Button(
            multi_row,
            text="确定",
            command=self._on_instance_count_confirm,
            font=self.fonts["base"],
            width=6,
            bg=self.colors["accent"],
            fg="white",
            activebackground=self.colors["accent_dark"],
            activeforeground="white",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
        ).pack(side=tk.LEFT)

        tk.Label(
            multi_frame,
            text="警告：请根据自身电脑性能，量力而行，最多80个。",
            font=self.fonts["small"],
            fg=self.colors["subtext"],
            bg=self.colors["card_bg"],
            anchor=tk.W,
        ).pack(anchor=tk.W, padx=2, pady=(6, 0))

        tk.Label(
            multi_frame,
            text="超过10个时，在此界面会暂停桌宠们。",
            font=self.fonts["small"],
            fg=self.colors["subtext"],
            bg=self.colors["card_bg"],
            anchor=tk.W,
        ).pack(anchor=tk.W, padx=2, pady=(6, 0))

        tk.Label(
            multi_frame,
            text=(f"如果设置太多导致软件崩溃无法启动"),
            font=self.fonts["small"],
            fg=self.colors["subtext"],
            bg=self.colors["card_bg"],
            anchor=tk.W,
        ).pack(anchor=tk.W, padx=2, pady=(2, 0))

        username = getpass.getuser()

        tk.Label(
            multi_frame,
            text=(f"请‘win+R’打开运行，输入'%appdata%/ameath_config.json'打开配置文件"),
            font=self.fonts["small"],
            fg=self.colors["subtext"],
            bg=self.colors["card_bg"],
            anchor=tk.W,
        ).pack(anchor=tk.W, padx=2, pady=(2, 0))

        tk.Label(
            multi_frame,
            text=(f"手动修改 instance_count 参数为1。"),
            font=self.fonts["small"],
            fg=self.colors["subtext"],
            bg=self.colors["card_bg"],
            anchor=tk.W,
        ).pack(anchor=tk.W, padx=2, pady=(2, 0))

        # ===== 游荡停驻设置 =====
        wander_idle_frame = tk.LabelFrame(
            inner_frame,
            text="游荡模式下是否停驻播放idle动作",
            font=self.fonts["subtitle"],
            padx=15,
            pady=12,
            bg=self.colors["card_bg"],
            fg=self.colors["accent_dark"],
            bd=1,
            relief=tk.SOLID,
        )
        wander_idle_frame.pack(fill=tk.X, pady=(0, 10), ipady=5)

        self.wander_idle_stay_mode_var = tk.IntVar(value=current_wander_idle_stay_mode)
        wander_idle_options = [
            ("始终移动", 0),
            ("概率停驻", 1),
            ("停驻", 2),
        ]
        for text, value in wander_idle_options:
            rb = tk.Radiobutton(
                wander_idle_frame,
                text=text,
                variable=self.wander_idle_stay_mode_var,
                value=value,
                font=self.fonts["control"],
                bg=self.colors["card_bg"],
                fg=self.colors["text"],
                activebackground=self.colors["card_bg"],
                activeforeground=self.colors["accent_dark"],
                selectcolor=self.colors["bg"],
                command=self._on_wander_idle_stay_mode_changed,
                anchor=tk.W,
            )
            rb.pack(anchor=tk.W, pady=2)

        return frame

    def _create_update_tab(self, parent):
        """创建检查更新标签页"""
        frame = ttk.Frame(parent, padding=20)
        frame.columnconfigure(0, weight=1)

        # 加载当前配置
        config = load_config()
        current_skip_updates = config.get("skip_updates", False)

        # 当前版本信息
        version_frame = tk.Frame(frame, bg=self.colors["bg"])
        version_frame.grid(row=0, column=0, sticky="ew", pady=(0, 15))

        tk.Label(
            version_frame,
            text=f"当前版本: {self.version}",
            font=self.fonts["title"],
            fg=self.colors["accent_dark"],
            bg=self.colors["bg"],
        ).pack(anchor=tk.W)

        # 分隔线
        separator = ttk.Separator(frame, orient="horizontal")
        separator.grid(row=1, column=0, sticky="ew", pady=12)

        # 检查更新按钮
        self.check_btn = tk.Button(
            frame,
            text="检查更新",
            command=self._on_check_update,
            font=self.fonts["subtitle"],
            width=14,
            bg=self.colors["accent"],
            fg="white",
            activebackground=self.colors["accent_dark"],
            activeforeground="white",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
        )
        self.check_btn.grid(row=2, column=0, pady=10)

        # 状态标签
        self.update_status_label = tk.Label(
            frame,
            text="点击上方按钮检查是否有新版本可用",
            font=self.fonts["base"],
            fg=self.colors["subtext"],
            bg=self.colors["bg"],
        )
        self.update_status_label.grid(row=3, column=0, pady=8)

        # 分隔线
        separator2 = ttk.Separator(frame, orient="horizontal")
        separator2.grid(row=4, column=0, sticky="ew", pady=12)

        # 更新信息区域
        info_container = tk.Frame(frame, bg=self.colors["bg"])
        info_container.grid(row=5, column=0, sticky="nsew", pady=5)
        frame.rowconfigure(5, weight=1)

        # 最新版本标签
        self.latest_version_label = tk.Label(
            info_container,
            text="",
            font=self.fonts["subtitle"],
            fg=self.colors["accent_dark"],
            bg=self.colors["bg"],
            anchor=tk.W,
        )
        self.latest_version_label.pack(fill=tk.X, pady=(0, 8))

        # 发布说明标签
        tk.Label(
            info_container,
            text="发布说明:",
            font=self.fonts["base"],
            fg=self.colors["accent_dark"],
            bg=self.colors["bg"],
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(0, 5))

        # 发布说明文本框（带边框和滚动条）
        text_frame = tk.Frame(
            info_container,
            bd=1,
            relief=tk.SOLID,
            bg=self.colors["border"],
        )
        text_frame.pack(fill=tk.BOTH, expand=True)

        self.release_notes_text = tk.Text(
            text_frame,
            height=9,
            wrap=tk.WORD,
            font=self.fonts["base"],
            state=tk.DISABLED,
            padx=10,
            pady=10,
            relief=tk.FLAT,
            bg=self.colors["card_bg"],
            fg=self.colors["text"],
            insertbackground=self.colors["accent_dark"],
        )
        self.release_notes_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 滚动条
        scrollbar = tk.Scrollbar(
            text_frame,
            command=self.release_notes_text.yview,
            width=14,
            bg=self.colors["tab_bg"],
            activebackground=self.colors["tab_active"],
            troughcolor=self.colors["card_bg"],
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.release_notes_text.config(yscrollcommand=scrollbar.set)

        # 操作按钮区域
        self.update_btn_frame = tk.Frame(frame, bg=self.colors["bg"])
        self.update_btn_frame.grid(row=6, column=0, sticky="ew", pady=(12, 0))

        # 下载和跳过按钮
        button_left = tk.Frame(self.update_btn_frame, bg=self.colors["bg"])
        button_left.pack(side=tk.LEFT)

        self.download_btn = tk.Button(
            button_left,
            text="下载并更新",
            command=self._on_download_update,
            font=self.fonts["base"],
            width=12,
            bg=self.colors["accent"],
            fg="white",
            activebackground=self.colors["accent_dark"],
            activeforeground="white",
            state=tk.DISABLED,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
        )
        self.download_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.skip_btn = tk.Button(
            button_left,
            text="跳过此版本",
            command=self._on_skip_version,
            font=self.fonts["base"],
            width=12,
            bg=self.colors["tab_bg"],
            fg=self.colors["accent_dark"],
            activebackground=self.colors["tab_active"],
            activeforeground=self.colors["accent_dark"],
            relief=tk.FLAT,
            bd=0,
            state=tk.DISABLED,
            cursor="hand2",
        )
        self.skip_btn.pack(side=tk.LEFT)

        # 不接收更新提醒复选框（右侧）
        self.skip_updates_var = tk.BooleanVar(value=current_skip_updates)
        skip_updates_cb = tk.Checkbutton(
            self.update_btn_frame,
            text="不接收更新提醒",
            variable=self.skip_updates_var,
            font=self.fonts["control"],
            bg=self.colors["bg"],
            fg=self.colors["text"],
            activebackground=self.colors["bg"],
            activeforeground=self.colors["accent_dark"],
            selectcolor=self.colors["bg"],
            command=self._on_skip_updates_changed,
        )
        skip_updates_cb.pack(side=tk.RIGHT)

        return frame

    def _create_about_tab(self, parent):
        """创建关于标签页"""
        frame = ttk.Frame(parent, padding=20)

        # 顶部留白
        tk.Frame(frame, height=15, bg=self.colors["bg"]).pack()

        # 显示 ameath.gif
        try:
            gif_image = Image.open(resource_path("gifs/ameath.gif"))
            gif_image = gif_image.resize((100, 100), Image.Resampling.LANCZOS)
            gif_photo = ImageTk.PhotoImage(gif_image)
            gif_label = tk.Label(frame, image=gif_photo, border=0, bg=self.colors["bg"])
            gif_label.image = gif_photo  # type: ignore[attr-defined]
            gif_label.pack(pady=(0, 15))
        except Exception as e:
            print(f"加载关于窗口GIF失败: {e}")

        # 标题
        tk.Label(
            frame,
            text="飞吧，朝向春天",
            font=("Microsoft YaHei UI", 20, "bold"),
            fg=self.colors["accent_dark"],
            bg=self.colors["bg"],
        ).pack(pady=(0, 10))

        # 版本号
        tk.Label(
            frame,
            text=f"版本 {self.version}",
            font=self.fonts["base"],
            fg=self.colors["subtext"],
            bg=self.colors["bg"],
        ).pack(pady=(0, 5))

        # Git Hash
        if self.git_hash:
            tk.Label(
                frame,
                text=f"Build: {self.git_hash}",
                font=self.fonts["small"],
                fg=self.colors["subtext"],
                bg=self.colors["bg"],
            ).pack(pady=(0, 15))
        else:
            tk.Frame(frame, height=10, bg=self.colors["bg"]).pack()

        # 分隔线
        separator = ttk.Separator(frame, orient="horizontal")
        separator.pack(fill=tk.X, pady=10)

        # 描述文本
        desc_frame = tk.Frame(frame, bg=self.colors["bg"])
        desc_frame.pack(pady=15)

        desc_lines = [
            '"爱弥斯，拉贝尔学部的隧者适格者！',
            "不过，那都是生前的事了。",
            '现在的我，是电子幽灵哦~"',
        ]

        for line in desc_lines:
            tk.Label(
                desc_frame,
                text=line,
                font=self.fonts["base"],
                fg=self.colors["text"],
                bg=self.colors["bg"],
                justify=tk.CENTER,
            ).pack(pady=2)

        # 分隔线
        separator2 = ttk.Separator(frame, orient="horizontal")
        separator2.pack(fill=tk.X, pady=10)

        # 链接区域
        links_frame = tk.Frame(frame, bg=self.colors["bg"])
        links_frame.pack(pady=10)

        # Gitee Release 链接
        link1 = tk.Frame(links_frame, bg=self.colors["bg"])
        link1.pack(pady=5)
        tk.Label(
            link1,
            text="软件发布页: ",
            font=self.fonts["base"],
            fg=self.colors["text"],
            bg=self.colors["bg"],
        ).pack(side=tk.LEFT)
        link1_text = tk.Label(
            link1,
            text="Gitee Release",
            font=self.fonts["base"],
            fg=self.colors["accent"],
            bg=self.colors["bg"],
            cursor="hand2",
        )
        link1_text.pack(side=tk.LEFT)
        link1_text.bind("<Button-1>", lambda e: webbrowser.open(GITEE_RELEASES_URL))

        # B站链接
        link2 = tk.Frame(links_frame, bg=self.colors["bg"])
        link2.pack(pady=5)
        tk.Label(
            link2,
            text="作者: ",
            font=self.fonts["base"],
            fg=self.colors["text"],
            bg=self.colors["bg"],
        ).pack(side=tk.LEFT)
        link2_text = tk.Label(
            link2,
            text="b站-fugu-",
            font=self.fonts["base"],
            fg=self.colors["accent"],
            bg=self.colors["bg"],
            cursor="hand2",
        )
        link2_text.pack(side=tk.LEFT)
        link2_text.bind(
            "<Button-1>",
            lambda e: webbrowser.open("https://space.bilibili.com/84508966"),
        )

        return frame

    def _on_scale_changed(self):
        """缩放值改变回调"""
        index = self.scale_var.get()
        self.app.set_scale(index)

    def _on_transparency_changed(self):
        """透明度值改变回调"""
        index = self.transparency_var.get()
        self.app.set_transparency(index)

    def _on_startup_changed(self):
        """开机自启改变回调"""
        enabled = self.auto_startup_var.get()
        self.app.auto_startup = enabled
        set_auto_startup(enabled)
        config = load_config()
        config["auto_startup"] = enabled
        save_config(config)

    def _on_voice_enabled_changed(self):
        """语音开关改变回调"""
        enabled = self.voice_enabled_var.get()
        config = load_config()
        config["voice_enabled"] = enabled
        save_config(config)
        # 通知应用更新语音设置
        if hasattr(self.app, "set_voice_enabled"):
            self.app.set_voice_enabled(enabled)

    def _on_voice_volume_changed(self, value):
        """语音音量改变回调"""
        volume = int(float(value))
        self.voice_volume_label.config(text=f"{volume}%")
        config = load_config()
        config["voice_volume"] = volume
        save_config(config)
        # 通知应用更新语音音量
        if hasattr(self.app, "set_voice_volume"):
            self.app.set_voice_volume(volume)

    def _on_music_enabled_changed(self):
        """音乐播放器开关改变回调"""
        enabled = self.music_enabled_var.get()
        config = load_config()
        config["music_enabled"] = enabled
        save_config(config)

        # 同步更新音乐标签页的 UI 状态
        if hasattr(self, "music_player_embedded") and self.music_player_embedded:
            self.music_player_embedded.music_enabled = enabled
            # 更新按钮状态
            state = tk.NORMAL if enabled else tk.DISABLED
            self.music_player_embedded.prev_btn.config(state=state)
            self.music_player_embedded.play_btn.config(state=state)
            self.music_player_embedded.next_btn.config(state=state)
            self.music_player_embedded.progress_bar.config(state=state)
            for btn in self.music_player_embedded.action_buttons:
                btn.config(state=state)

    def _on_music_volume_changed(self, value):
        """音乐音量改变回调"""
        volume = int(float(value))
        self.music_volume_label.config(text=f"{volume}%")
        config = load_config()
        config["music_volume"] = volume
        save_config(config)

    def _on_display_mode_changed(self):
        """显示模式改变回调（固定屏幕/跨屏游荡）"""
        self._update_screen_options_visibility()
        # 保存配置
        display_mode = self.display_mode_var.get()
        is_wander = display_mode == "wander"
        config = load_config()
        config["total_screen"] = is_wander
        save_config(config)

    def _update_screen_options_visibility(self):
        """更新屏幕选项的可用状态"""
        if not hasattr(self, "screen_select_container"):
            return

        display_mode = self.display_mode_var.get()

        if display_mode == "wander":
            # 跨屏游荡：禁用屏幕选择
            self._set_screen_select_state(tk.DISABLED)
        else:
            # 固定屏幕：启用屏幕选择
            self._set_screen_select_state(tk.NORMAL)

    def _set_screen_select_state(self, state):
        """设置屏幕选择区域的状态"""
        if hasattr(self, "screen_select_container"):
            for child in self.screen_select_container.winfo_children():
                if isinstance(child, tk.Radiobutton):
                    child.config(state=state)
                elif isinstance(child, tk.Frame):
                    for rb in child.winfo_children():
                        if isinstance(rb, tk.Radiobutton):
                            rb.config(state=state)

    def _on_screen_changed(self):
        """屏幕索引改变回调"""
        index = self.screen_var.get()
        config = load_config()
        config["screen_index"] = index
        save_config(config)

    def _on_display_priority_changed(self):
        """显示优先级变化回调"""
        mode = self.display_priority_var.get()
        self.app.set_display_priority(mode)

    def _on_wander_idle_stay_mode_changed(self):
        """游荡停驻模式变化回调"""
        mode = self.wander_idle_stay_mode_var.get()
        self.app.set_wander_idle_stay_mode(mode)

    def _on_instance_count_confirm(self):
        """多开数量确认"""
        try:
            count = int(self.instance_count_var.get())
        except ValueError:
            count = 1
        if count < 1:
            count = 1
        if count > 80:
            count = 80
            messagebox.showwarning("警告", "实例数量不能超过80个，已自动设置为80。")
        self.instance_count_var.set(str(count))
        config = load_config()
        config["instance_count"] = count
        save_config(config)

        # 如果设置的实例数大于10，暂停所有桌宠以保证设置窗口流畅
        if count > 10 and not self.app.is_paused:
            self.app.toggle_pause()
            self._pets_paused_by_settings = True

        if hasattr(self.app, "set_instance_count"):
            self.app.set_instance_count(count)

    def _on_check_update(self):
        """检查更新按钮回调"""
        self.check_btn.config(state=tk.DISABLED)
        self.update_status_label.config(
            text="正在检查更新，请稍候...", fg=self.colors["accent_dark"]
        )
        self.download_btn.config(state=tk.DISABLED)
        self.skip_btn.config(state=tk.DISABLED)
        self.latest_version = None
        self._latest_asset_url = None
        self._latest_asset_name = None

        # 在新线程中检查更新
        self._update_check_thread = threading.Thread(
            target=self._do_check_update, daemon=True
        )
        self._update_check_thread.start()

    def _do_check_update(self):
        """执行更新检查（在后台线程）"""
        try:
            result = check_update(self.version)
            # 使用 after 方法回到主线程更新 UI
            if self.window and self.window.winfo_exists():
                self.window.after(0, lambda: self._on_update_result(result))
        except Exception as e:
            if self.window and self.window.winfo_exists():
                self.window.after(
                    0,
                    lambda: self._on_update_error(str(e)),
                )

    def _on_update_result(self, result):
        """更新检查结果回调"""
        self.check_btn.config(state=tk.NORMAL)

        if result is None:
            self.update_status_label.config(
                text="检查更新失败，请稍后重试", fg="#D24B4B"
            )
            return

        latest_version, release_notes, asset_url, asset_name = result
        self.latest_version = latest_version
        self._latest_asset_url = asset_url
        self._latest_asset_name = asset_name

        # 比较版本号
        current_parts = self.version.split(".")
        latest_parts = latest_version.split(".")

        is_newer = False
        for c, l in zip(current_parts, latest_parts):
            try:
                if int(l) > int(c):
                    is_newer = True
                    break
                elif int(l) < int(c):
                    break
            except ValueError:
                continue
        else:
            if len(latest_parts) > len(current_parts):
                is_newer = True

        if is_newer:
            self.update_status_label.config(
                text="发现新版本可用！", fg=self.colors["accent"]
            )
            self.latest_version_label.config(text=f"最新版本: {latest_version}")

            # 显示发布说明
            self.release_notes_text.config(state=tk.NORMAL)
            self.release_notes_text.delete("1.0", tk.END)
            self.release_notes_text.insert(tk.END, release_notes or "暂无发布说明")
            self.release_notes_text.config(state=tk.DISABLED)

            # 启用下载按钮
            if self._latest_asset_url:
                self.download_btn.config(state=tk.NORMAL)
            else:
                self.download_btn.config(state=tk.DISABLED)
                self.update_status_label.config(
                    text="未找到可下载的更新文件", fg="#D24B4B"
                )
            self.skip_btn.config(state=tk.NORMAL)
        else:
            self.update_status_label.config(
                text="当前已是最新版本", fg=self.colors["accent"]
            )
            self.latest_version_label.config(text="")
            self.latest_version = None
            self._latest_asset_url = None
            self._latest_asset_name = None
            self.release_notes_text.config(state=tk.NORMAL)
            self.release_notes_text.delete("1.0", tk.END)
            self.release_notes_text.insert(tk.END, "您正在使用最新版本，无需更新。")
            self.release_notes_text.config(state=tk.DISABLED)

    def _on_download_update(self):
        """下载并更新"""
        if not self._latest_asset_url or not self._latest_asset_name:
            self.update_status_label.config(text="未找到可下载的更新文件", fg="#D24B4B")
            return

        self.download_btn.config(state=tk.DISABLED)
        self.skip_btn.config(state=tk.DISABLED)
        self.check_btn.config(state=tk.DISABLED)
        self.update_status_label.config(
            text="正在下载更新，请稍候...", fg=self.colors["accent_dark"]
        )

        self._download_thread = threading.Thread(
            target=self._do_download_update, daemon=True
        )
        self._download_thread.start()

    def _do_download_update(self):
        """执行下载并更新（后台线程）"""
        error = download_and_update(self._latest_asset_url, self._latest_asset_name)
        if self.window and self.window.winfo_exists():
            if error:
                self.window.after(0, lambda: self._on_update_error(error))
            else:
                self.window.after(0, self._on_update_ready)

    def _on_update_ready(self):
        """下载完成，准备更新"""
        self.update_status_label.config(
            text="下载完成，已更新，请手动重新打开程序", fg=self.colors["accent"]
        )
        self.download_btn.config(text="更新完成，请手动启动", state=tk.DISABLED)
        self.skip_btn.config(state=tk.DISABLED)
        messagebox.showinfo("更新完成", "更新已完成，请手动重新打开程序。")
        if self.app:
            if hasattr(self.app, "request_quit"):
                self.app.request_quit()
            else:
                self.app._request_quit = True
        if self.window:
            self.window.destroy()

    def _on_update_error(self, error_msg):
        """更新检查错误回调"""
        self.check_btn.config(state=tk.NORMAL)
        self.update_status_label.config(text=f"检查失败: {error_msg}", fg="#D24B4B")

    def _on_skip_version(self):
        """跳过此版本"""
        if not self.latest_version:
            self.update_status_label.config(
                text="当前没有可跳过的版本", fg=self.colors["accent_dark"]
            )
            return
        config = load_config()
        config["skip_version"] = self.latest_version
        save_config(config)
        self.skip_btn.config(state=tk.DISABLED)
        self.update_status_label.config(
            text=f"已设置为不再提醒版本 {self.latest_version}",
            fg=self.colors["accent_dark"],
        )

    def _on_skip_updates_changed(self):
        """不接收更新提醒复选框变化回调"""
        enabled = self.skip_updates_var.get()
        config = load_config()
        config["skip_updates"] = enabled
        save_config(config)
        if enabled:
            self.update_status_label.config(
                text="已关闭更新提醒", fg=self.colors["accent_dark"]
            )
        else:
            self.update_status_label.config(
                text="已开启更新提醒", fg=self.colors["accent"]
            )

    def _create_music_tab(self, parent):
        """创建音乐播放器标签页 - 歌姬偶像风格"""
        frame = tk.Frame(parent, bg=self.colors["bg"])

        # 创建内嵌音乐播放器（使用统一风格）
        self.music_player_embedded = MusicPlayerEmbedded(frame, self.colors, self.fonts)

        return frame


class MusicPlayerEmbedded:
    """内嵌音乐播放器 - 歌姬偶像风格"""

    def __init__(self, parent, colors, fonts):
        self.parent = parent
        self.colors = colors
        self.fonts = fonts
        self.config = load_config()

        # 创建实际的播放器核心（使用 MusicPlayer 的音频功能）
        from .music_player import MusicPlayer

        # 创建一个隐藏的 Frame 作为 parent，确保 MusicPlayer 正常初始化
        import tkinter as tk

        dummy_frame = tk.Frame(parent)
        self.core_player = MusicPlayer(
            parent=dummy_frame, position_unlock_callback=None
        )

        # 同步音乐文件列表
        self.music_files = self.core_player.music_files
        self.current_index = self.core_player.current_index
        self.is_playing = self.core_player.is_playing
        self.is_paused = self.core_player.is_paused

        # 从配置加载
        self.music_volume = self.config.get("music_volume", 100)
        self.music_enabled = self.config.get("music_enabled", False)

        # 应用音量设置
        self.core_player.music_volume = self.music_volume

        # 创建UI
        self._create_ui()

        # 加载音乐文件并更新列表显示
        self._load_music_files()

        # 启动进度更新循环
        self._start_progress_loop()

    def _create_ui(self):
        """创建音乐播放器UI - 歌姬偶像风格"""
        # 主容器
        main_frame = tk.Frame(self.parent, bg=self.colors["bg"])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        # ===== 演出曲目列表 =====
        playlist_frame = tk.LabelFrame(
            main_frame,
            text="🎵 演出曲目",
            font=self.fonts["subtitle"],
            padx=15,
            pady=12,
            bg=self.colors["card_bg"],
            fg=self.colors["accent_dark"],
            bd=1,
            relief=tk.SOLID,
        )
        playlist_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15), ipady=5)

        # 列表框容器
        list_container = tk.Frame(playlist_frame, bg=self.colors["card_bg"])
        list_container.pack(fill=tk.BOTH, expand=True, pady=5)

        # 滚动条
        scrollbar = tk.Scrollbar(list_container, bg=self.colors["card_bg"])
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 歌单列表 - 像素风边框，固定显示5首歌高度
        self.listbox = tk.Listbox(
            list_container,
            yscrollcommand=scrollbar.set,
            bg=self.colors["bg"],
            fg=self.colors["text"],
            selectbackground=self.colors["accent"],
            selectforeground="white",
            font=self.fonts["base"],
            bd=2,
            relief=tk.SUNKEN,
            highlightthickness=0,
            activestyle="none",
            width=45,
        )
        self.listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        scrollbar.config(command=self.listbox.yview)

        self.listbox.bind("<Double-Button-1>", self._on_double_click)

        # ===== 演出控制台 =====
        console_frame = tk.LabelFrame(
            main_frame,
            text="🎮 演出控制台",
            font=self.fonts["subtitle"],
            padx=15,
            pady=12,
            bg=self.colors["card_bg"],
            fg=self.colors["accent_dark"],
            bd=1,
            relief=tk.SOLID,
        )
        console_frame.pack(fill=tk.X, pady=(0, 15), ipady=5)

        # 播放控制按钮 - 偶像风格
        btn_row = tk.Frame(console_frame, bg=self.colors["card_bg"])
        btn_row.pack(fill=tk.X, pady=(0, 10))

        # 统一按钮样式
        # 统一按钮样式 - 演出控制台
        base_btn = {
            "bg": self.colors["accent"],
            "fg": "white",
            "activebackground": self.colors["accent_dark"],
            "activeforeground": "white",
            "font": self.fonts["control"],
            "relief": tk.FLAT,
            "bd": 0,
            "cursor": "hand2",
            "height": 1,
        }

        self.prev_btn = tk.Button(
            btn_row,
            text="◀◀ 上一曲",
            width=10,
            command=self._previous_track,
            **base_btn,
            state=tk.NORMAL if self.music_enabled else tk.DISABLED,
        )
        self.prev_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.play_btn = tk.Button(
            btn_row,
            text="▶ 演出开始",
            width=12,
            command=self._toggle_play,
            **base_btn,
            state=tk.NORMAL if self.music_enabled else tk.DISABLED,
        )
        self.play_btn.pack(side=tk.LEFT, padx=5)

        self.next_btn = tk.Button(
            btn_row,
            text="下一曲 ▶▶",
            width=10,
            command=self._next_track,
            **base_btn,
            state=tk.NORMAL if self.music_enabled else tk.DISABLED,
        )
        self.next_btn.pack(side=tk.LEFT, padx=(10, 0))

        # 进度条 - 演出进度
        progress_row = tk.Frame(console_frame, bg=self.colors["card_bg"])
        progress_row.pack(fill=tk.X, pady=(10, 5))

        tk.Label(
            progress_row,
            text="演出进度: ",
            font=self.fonts["control"],
            bg=self.colors["card_bg"],
            fg=self.colors["text"],
        ).pack(side=tk.LEFT)

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = tk.Scale(
            progress_row,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            variable=self.progress_var,
            command=self._on_progress_change,
            length=300,
            font=self.fonts["small"],
            bg=self.colors["card_bg"],
            fg=self.colors["text"],
            highlightthickness=0,
            troughcolor=self.colors["tab_bg"],
            activebackground=self.colors["accent"],
            sliderrelief=tk.FLAT,
            state=tk.NORMAL if self.music_enabled else tk.DISABLED,
        )
        self.progress_bar.pack(side=tk.LEFT, padx=(5, 10))

        self.time_label = tk.Label(
            progress_row,
            text="0:00 / 0:00",
            font=self.fonts["control"],
            bg=self.colors["card_bg"],
            fg=self.colors["accent_dark"],
            width=12,
        )
        self.time_label.pack(side=tk.LEFT)

        # ===== 音量与资源管理 =====
        settings_frame = tk.LabelFrame(
            main_frame,
            text="🔧 音效设定",
            font=self.fonts["subtitle"],
            padx=15,
            pady=12,
            bg=self.colors["card_bg"],
            fg=self.colors["accent_dark"],
            bd=1,
            relief=tk.SOLID,
        )
        settings_frame.pack(fill=tk.X, pady=(0, 10), ipady=5)

        # 音量控制
        volume_row = tk.Frame(settings_frame, bg=self.colors["card_bg"])
        volume_row.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            volume_row,
            text="场馆音量: ",
            font=self.fonts["control"],
            bg=self.colors["card_bg"],
            fg=self.colors["text"],
        ).pack(side=tk.LEFT)

        self.volume_var = tk.IntVar(value=self.music_volume)
        volume_scale = tk.Scale(
            volume_row,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            variable=self.volume_var,
            command=self._on_volume_change,
            length=250,
            font=self.fonts["small"],
            bg=self.colors["card_bg"],
            fg=self.colors["text"],
            highlightthickness=0,
            troughcolor=self.colors["tab_bg"],
            activebackground=self.colors["accent"],
            sliderrelief=tk.FLAT,
            state=tk.NORMAL if self.music_enabled else tk.DISABLED,
        )
        volume_scale.pack(side=tk.LEFT, padx=(5, 10))

        self.volume_label = tk.Label(
            volume_row,
            text=f"{self.music_volume}%",
            font=self.fonts["control"],
            bg=self.colors["card_bg"],
            fg=self.colors["accent_dark"],
            width=5,
        )
        self.volume_label.pack(side=tk.LEFT)

        # 资源管理按钮
        resource_row = tk.Frame(settings_frame, bg=self.colors["card_bg"])
        resource_row.pack(fill=tk.X)

        secondary_btn_style = {
            "bg": self.colors["tab_bg"],
            "fg": self.colors["text"],
            "activebackground": self.colors["tab_active"],
            "activeforeground": self.colors["accent_dark"],
            "font": self.fonts["base"],
            "relief": tk.FLAT,
            "bd": 0,
            "cursor": "hand2",
            "width": 12,
            "height": 1,
        }

        refresh_btn = tk.Button(
            resource_row,
            text="🔄 刷新曲目",
            command=self._refresh_list,
            **secondary_btn_style,
            state=tk.NORMAL if self.music_enabled else tk.DISABLED,
        )
        refresh_btn.pack(side=tk.LEFT, padx=(0, 10))

        import_btn = tk.Button(
            resource_row,
            text="📥 导入曲目",
            command=self._import_music,
            **secondary_btn_style,
            state=tk.NORMAL if self.music_enabled else tk.DISABLED,
        )
        import_btn.pack(side=tk.LEFT)

        # 保存按钮引用
        self.action_buttons = [refresh_btn, import_btn]

    def _load_music_files(self):
        """加载音乐文件列表"""
        import os
        from .utils import resource_path

        music_dir = resource_path("sound/music")
        self.music_files = []

        if os.path.exists(music_dir):
            for file in sorted(os.listdir(music_dir)):
                if file.lower().endswith((".wav", ".mp3")):
                    self.music_files.append(os.path.join(music_dir, file))

        # 同步到核心播放器
        self.core_player.music_files = self.music_files
        self.core_player.load_music_files_internal()

        self._update_listbox()

    def _update_listbox(self):
        """更新列表框显示"""
        import os

        self.listbox.delete(0, tk.END)
        for file in self.music_files:
            self.listbox.insert(tk.END, f" ♪ {os.path.basename(file)}")

        if self.current_index >= 0 and self.current_index < len(self.music_files):
            self.listbox.selection_set(self.current_index)
            self.listbox.see(self.current_index)

    def _on_progress_change(self, value):
        """进度条拖动"""
        if not self.music_files or self.current_index < 0:
            return

        # 调用核心播放器的进度跳转
        self.core_player.on_progress_change(value)

    def _on_volume_change(self, value):
        """音量改变"""
        volume = int(float(value))
        self.music_volume = volume
        self.volume_label.config(text=f"{volume}%")

        # 同步到核心播放器，实时调整音量
        self.core_player.music_volume = volume

        config = load_config()
        config["music_volume"] = volume
        save_config(config)

    def _on_double_click(self, event):
        """双击播放"""
        if not self.music_enabled:
            return
        selection = self.listbox.curselection()
        if selection:
            self.current_index = selection[0]
            self._play_current()

    def _toggle_play(self):
        """播放/暂停切换"""
        if not self.music_enabled:
            return
        if self.is_playing:
            self._pause()
        else:
            self._play_current()

    def _play_current(self):
        """播放当前选中的歌曲"""
        if not self.music_files or self.current_index < 0:
            return

        # 同步当前索引到核心播放器
        self.core_player.current_index = self.current_index
        self.core_player.music_files = self.music_files

        # 调用核心播放器播放
        self.core_player.play_current_track()

        # 更新UI状态
        self.is_playing = self.core_player.is_playing
        self.is_paused = self.core_player.is_paused
        self.play_btn.config(text="⏸ 暂停演出")

    def _pause(self):
        """暂停播放"""
        # 调用核心播放器暂停
        self.core_player.toggle_play_pause()

        # 更新UI状态
        self.is_playing = self.core_player.is_playing
        self.is_paused = self.core_player.is_paused
        self.play_btn.config(text="▶ 继续演出")

    def _previous_track(self):
        """上一首"""
        if not self.music_files:
            return
        self.current_index = (self.current_index - 1) % len(self.music_files)
        self._update_listbox()
        if self.is_playing:
            self._play_current()

    def _next_track(self):
        """下一首"""
        if not self.music_files:
            return
        self.current_index = (self.current_index + 1) % len(self.music_files)
        self._update_listbox()
        if self.is_playing:
            self._play_current()

    def _start_progress_loop(self):
        """启动进度更新循环"""
        self._update_progress_ui()

    def _update_progress_ui(self):
        """更新进度UI"""
        try:
            if self.core_player.is_playing and not self.core_player.is_paused:
                # 更新播放按钮状态
                if self.play_btn.cget("text") != "⏸ 暂停演出":
                    self.play_btn.config(text="⏸ 暂停演出")

                # 更新进度条（如果有进度信息）
                if self.core_player.total_length > 0 and self.core_player.sample_rate:
                    # 用 sample_rate 和 current_position 计算进度
                    current_ms = int(
                        self.core_player.current_position
                        * 1000
                        / self.core_player.sample_rate
                    )
                    progress = (
                        (current_ms / self.core_player.total_length) * 100
                        if self.core_player.total_length > 0
                        else 0
                    )
                    self.progress_var.set(min(progress, 100))

                    # 更新时间显示
                    self.time_label.config(
                        text=f"{self._format_time(current_ms)} / {self._format_time(self.core_player.total_length)}"
                    )
            else:
                # 更新播放按钮状态
                if (
                    self.core_player.is_paused
                    and self.play_btn.cget("text") != "▶ 继续演出"
                ):
                    self.play_btn.config(text="▶ 继续演出")

            # 继续循环 - 检查窗口是否还存在
            if hasattr(self, "parent") and self.parent.winfo_exists():
                self.parent.after(100, self._update_progress_ui)
        except Exception as e:
            # 静默处理更新错误，继续循环
            if hasattr(self, "parent"):
                try:
                    if self.parent.winfo_exists():
                        self.parent.after(100, self._update_progress_ui)
                except Exception:
                    pass

    def _format_time(self, ms):
        """格式化时间显示"""
        seconds = ms // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}:{seconds:02d}"

    def _refresh_list(self):
        """刷新音乐列表"""
        self._load_music_files()

    def _import_music(self):
        """导入音乐文件"""
        import os
        import shutil
        from tkinter import filedialog
        from .utils import resource_path

        files = filedialog.askopenfilenames(
            title="选择音乐文件",
            filetypes=[
                ("音频文件", "*.wav *.mp3"),
                ("WAV文件", "*.wav"),
                ("MP3文件", "*.mp3"),
                ("所有文件", "*.*"),
            ],
        )

        if files:
            music_dir = resource_path("sound/music")
            os.makedirs(music_dir, exist_ok=True)

            for file in files:
                try:
                    shutil.copy(file, music_dir)
                except Exception as e:
                    print(f"复制文件失败 {file}: {e}")

            self._load_music_files()


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
