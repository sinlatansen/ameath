"""设置窗口模块 - 包含个性化、检查更新、关于三个标签页"""

import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
import webbrowser
import threading

from PIL import Image, ImageTk

from .config import load_config, save_config, set_auto_startup
from .constants import (
    SCALE_OPTIONS,
    TRANSPARENCY_OPTIONS,
    GITEE_RELEASES_URL,
    DEFAULT_SCALE_INDEX,
    DEFAULT_TRANSPARENCY_INDEX,
    DEFAULT_WANDER_IDLE_STAY_MODE,
)
from .utils import resource_path, check_update, download_and_update


class SettingsWindow:
    """设置窗口类"""

    def __init__(self, parent, app, version):
        self.parent = parent
        self.app = app
        self.version = version
        self.window = None
        self._update_check_thread = None
        self.notebook = None
        self.update_frame = None
        self.latest_version = None
        self._latest_asset_url = None
        self._latest_asset_name = None
        self._download_thread = None
        self._restore_display_priority = None
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
        # 窗口尺寸: 1000x800（自适应屏幕）
        self.window.update_idletasks()
        screen_w = self.window.winfo_screenwidth()
        screen_h = self.window.winfo_screenheight()
        window_w = min(1000, max(600, screen_w - 80))
        window_h = min(800, max(520, screen_h - 80))
        self.window.geometry(f"{window_w}x{window_h}")
        self.window.minsize(min(900, window_w), min(650, window_h))
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

        self._create_window()
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
        if self.window:
            self.window.destroy()
            self.window = None

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
            text="提示：每个实例约需要60MB运行内存，量力而行",
            font=self.fonts["small"],
            fg=self.colors["subtext"],
            bg=self.colors["card_bg"],
            anchor=tk.W,
        ).pack(anchor=tk.W, padx=2, pady=(6, 0))

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
        ).pack(pady=(0, 20))

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
        self.instance_count_var.set(str(count))
        config = load_config()
        config["instance_count"] = count
        save_config(config)
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


def show_settings_dialog(parent, app, version):
    """显示设置对话框的便捷函数"""
    settings = SettingsWindow(parent, app, version)
    settings.show()
