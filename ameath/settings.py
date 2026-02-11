"""设置窗口模块 - 包含个性化、检查更新、关于三个标签页"""

import tkinter as tk
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
)
from .utils import resource_path, check_update


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
        main_frame = tk.Frame(self.window)
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
        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(15, 0))

        tk.Button(
            btn_frame,
            text="确定",
            command=self._on_close,
            width=12,
            font=("Microsoft YaHei UI", 10),
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
        if self.window:
            self.window.destroy()
            self.window = None

    def _create_personalization_tab(self, parent):
        """创建个性化标签页"""
        frame = ttk.Frame(parent, padding=20)

        # 加载当前配置
        config = load_config()
        current_scale_idx = config.get("scale_index", DEFAULT_SCALE_INDEX)
        current_transparency_idx = config.get(
            "transparency_index", DEFAULT_TRANSPARENCY_INDEX
        )
        current_auto_startup = config.get("auto_startup", False)

        # ===== 缩放设置 =====
        scale_frame = tk.LabelFrame(
            frame,
            text="缩放比例",
            font=("Microsoft YaHei UI", 11, "bold"),
            padx=15,
            pady=12,
        )
        scale_frame.pack(fill=tk.X, pady=(0, 15), ipady=5)

        self.scale_var = tk.IntVar(value=current_scale_idx)

        # 使用网格布局，多列展示
        scale_grid = tk.Frame(scale_frame)
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
                font=("Microsoft YaHei UI", 10),
                command=self._on_scale_changed,
                anchor=tk.W,
            )
            rb.grid(row=row, column=col, sticky=tk.W, padx=15, pady=6)

        # ===== 透明度设置 =====
        trans_frame = tk.LabelFrame(
            frame,
            text="窗口透明度",
            font=("Microsoft YaHei UI", 11, "bold"),
            padx=15,
            pady=12,
        )
        trans_frame.pack(fill=tk.X, pady=(0, 15), ipady=5)

        self.transparency_var = tk.IntVar(value=current_transparency_idx)

        # 使用网格布局，多列展示
        trans_grid = tk.Frame(trans_frame)
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
                font=("Microsoft YaHei UI", 10),
                command=self._on_transparency_changed,
                anchor=tk.W,
            )
            rb.grid(row=row, column=col, sticky=tk.W, padx=20, pady=6)

        # ===== 开机自启设置 =====
        startup_frame = tk.LabelFrame(
            frame,
            text="启动选项",
            font=("Microsoft YaHei UI", 11, "bold"),
            padx=15,
            pady=12,
        )
        startup_frame.pack(fill=tk.X, pady=(0, 10), ipady=5)

        self.auto_startup_var = tk.BooleanVar(value=current_auto_startup)
        startup_cb = tk.Checkbutton(
            startup_frame,
            text="开机时自动启动程序",
            variable=self.auto_startup_var,
            font=("Microsoft YaHei UI", 10),
            command=self._on_startup_changed,
            anchor=tk.W,
        )
        startup_cb.pack(anchor=tk.W, pady=3)

        # 添加说明文字
        tk.Label(
            startup_frame,
            text="开启后，系统启动时将自动运行桌面宠物",
            font=("Microsoft YaHei UI", 9),
            fg="#666666",
            anchor=tk.W,
        ).pack(anchor=tk.W, padx=22)

        return frame

    def _create_update_tab(self, parent):
        """创建检查更新标签页"""
        frame = ttk.Frame(parent, padding=20)
        frame.columnconfigure(0, weight=1)

        # 加载当前配置
        config = load_config()
        current_skip_updates = config.get("skip_updates", False)

        # 当前版本信息
        version_frame = tk.Frame(frame)
        version_frame.grid(row=0, column=0, sticky="ew", pady=(0, 15))

        tk.Label(
            version_frame,
            text=f"当前版本: {self.version}",
            font=("Microsoft YaHei UI", 12),
        ).pack(anchor=tk.W)

        # 分隔线
        separator = ttk.Separator(frame, orient="horizontal")
        separator.grid(row=1, column=0, sticky="ew", pady=12)

        # 检查更新按钮
        self.check_btn = tk.Button(
            frame,
            text="检查更新",
            command=self._on_check_update,
            font=("Microsoft YaHei UI", 11),
            width=14,
            bg="#1890FF",
            fg="white",
            cursor="hand2",
        )
        self.check_btn.grid(row=2, column=0, pady=10)

        # 状态标签
        self.update_status_label = tk.Label(
            frame,
            text="点击上方按钮检查是否有新版本可用",
            font=("Microsoft YaHei UI", 10),
            fg="#666666",
        )
        self.update_status_label.grid(row=3, column=0, pady=8)

        # 分隔线
        separator2 = ttk.Separator(frame, orient="horizontal")
        separator2.grid(row=4, column=0, sticky="ew", pady=12)

        # 更新信息区域
        info_container = tk.Frame(frame)
        info_container.grid(row=5, column=0, sticky="nsew", pady=5)
        frame.rowconfigure(5, weight=1)

        # 最新版本标签
        self.latest_version_label = tk.Label(
            info_container,
            text="",
            font=("Microsoft YaHei UI", 11, "bold"),
            anchor=tk.W,
        )
        self.latest_version_label.pack(fill=tk.X, pady=(0, 8))

        # 发布说明标签
        tk.Label(
            info_container,
            text="发布说明:",
            font=("Microsoft YaHei UI", 10),
            fg="#333333",
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(0, 5))

        # 发布说明文本框（带边框和滚动条）
        text_frame = tk.Frame(info_container, bd=1, relief=tk.SOLID, bg="#cccccc")
        text_frame.pack(fill=tk.BOTH, expand=True)

        self.release_notes_text = tk.Text(
            text_frame,
            height=9,
            wrap=tk.WORD,
            font=("Microsoft YaHei UI", 10),
            state=tk.DISABLED,
            padx=10,
            pady=10,
            relief=tk.FLAT,
            bg="#fafafa",
        )
        self.release_notes_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 滚动条
        scrollbar = tk.Scrollbar(
            text_frame, command=self.release_notes_text.yview, width=14
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.release_notes_text.config(yscrollcommand=scrollbar.set)

        # 操作按钮区域
        self.update_btn_frame = tk.Frame(frame)
        self.update_btn_frame.grid(row=6, column=0, sticky="ew", pady=(12, 0))

        # 下载和跳过按钮
        button_left = tk.Frame(self.update_btn_frame)
        button_left.pack(side=tk.LEFT)

        self.download_btn = tk.Button(
            button_left,
            text="前往下载",
            command=lambda: webbrowser.open(GITEE_RELEASES_URL),
            font=("Microsoft YaHei UI", 10),
            width=12,
            bg="#1890FF",
            fg="white",
            state=tk.DISABLED,
            cursor="hand2",
        )
        self.download_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.skip_btn = tk.Button(
            button_left,
            text="跳过此版本",
            command=self._on_skip_version,
            font=("Microsoft YaHei UI", 10),
            width=12,
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
            font=("Microsoft YaHei UI", 10),
            command=self._on_skip_updates_changed,
        )
        skip_updates_cb.pack(side=tk.RIGHT)

        return frame

    def _create_about_tab(self, parent):
        """创建关于标签页"""
        frame = ttk.Frame(parent, padding=20)

        # 顶部留白
        tk.Frame(frame, height=15).pack()

        # 显示 ameath.gif
        try:
            gif_image = Image.open(resource_path("gifs/ameath.gif"))
            gif_image = gif_image.resize((100, 100), Image.Resampling.LANCZOS)
            gif_photo = ImageTk.PhotoImage(gif_image)
            gif_label = tk.Label(frame, image=gif_photo, border=0)
            gif_label.image = gif_photo  # type: ignore[attr-defined]
            gif_label.pack(pady=(0, 15))
        except Exception as e:
            print(f"加载关于窗口GIF失败: {e}")

        # 标题
        tk.Label(
            frame,
            text="飞吧，朝向春天",
            font=("Microsoft YaHei UI", 20, "bold"),
        ).pack(pady=(0, 10))

        # 版本号
        tk.Label(
            frame,
            text=f"版本 {self.version}",
            font=("Microsoft YaHei UI", 11),
            fg="#666666",
        ).pack(pady=(0, 20))

        # 分隔线
        separator = ttk.Separator(frame, orient="horizontal")
        separator.pack(fill=tk.X, pady=10)

        # 描述文本
        desc_frame = tk.Frame(frame)
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
                font=("Microsoft YaHei UI", 11),
                fg="#555555",
                justify=tk.CENTER,
            ).pack(pady=2)

        # 分隔线
        separator2 = ttk.Separator(frame, orient="horizontal")
        separator2.pack(fill=tk.X, pady=10)

        # 链接区域
        links_frame = tk.Frame(frame)
        links_frame.pack(pady=10)

        # Gitee Release 链接
        link1 = tk.Frame(links_frame)
        link1.pack(pady=5)
        tk.Label(
            link1,
            text="软件发布页: ",
            font=("Microsoft YaHei UI", 11),
        ).pack(side=tk.LEFT)
        link1_text = tk.Label(
            link1,
            text="Gitee Release",
            font=("Microsoft YaHei UI", 11),
            fg="#1890FF",
            cursor="hand2",
        )
        link1_text.pack(side=tk.LEFT)
        link1_text.bind("<Button-1>", lambda e: webbrowser.open(GITEE_RELEASES_URL))

        # B站链接
        link2 = tk.Frame(links_frame)
        link2.pack(pady=5)
        tk.Label(
            link2,
            text="作者: ",
            font=("Microsoft YaHei UI", 11),
        ).pack(side=tk.LEFT)
        link2_text = tk.Label(
            link2,
            text="b站-fugu-",
            font=("Microsoft YaHei UI", 11),
            fg="#1890FF",
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

    def _on_check_update(self):
        """检查更新按钮回调"""
        self.check_btn.config(state=tk.DISABLED)
        self.update_status_label.config(text="正在检查更新，请稍候...", fg="blue")
        self.download_btn.config(state=tk.DISABLED)
        self.skip_btn.config(state=tk.DISABLED)
        self.latest_version = None

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
            self.update_status_label.config(text="检查更新失败，请稍后重试", fg="red")
            return

        latest_version, release_notes = result
        self.latest_version = latest_version

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
            self.update_status_label.config(text="发现新版本可用！", fg="#52c41a")
            self.latest_version_label.config(text=f"最新版本: {latest_version}")

            # 显示发布说明
            self.release_notes_text.config(state=tk.NORMAL)
            self.release_notes_text.delete("1.0", tk.END)
            self.release_notes_text.insert(tk.END, release_notes or "暂无发布说明")
            self.release_notes_text.config(state=tk.DISABLED)

            # 启用下载按钮
            self.download_btn.config(state=tk.NORMAL)
            self.skip_btn.config(state=tk.NORMAL)
        else:
            self.update_status_label.config(text="当前已是最新版本", fg="#52c41a")
            self.latest_version_label.config(text="")
            self.latest_version = None
            self.release_notes_text.config(state=tk.NORMAL)
            self.release_notes_text.delete("1.0", tk.END)
            self.release_notes_text.insert(tk.END, "您正在使用最新版本，无需更新。")
            self.release_notes_text.config(state=tk.DISABLED)

    def _on_update_error(self, error_msg):
        """更新检查错误回调"""
        self.check_btn.config(state=tk.NORMAL)
        self.update_status_label.config(text=f"检查失败: {error_msg}", fg="red")

    def _on_skip_version(self):
        """跳过此版本"""
        if not self.latest_version:
            self.update_status_label.config(text="当前没有可跳过的版本", fg="#fa8c16")
            return
        config = load_config()
        config["skip_version"] = self.latest_version
        save_config(config)
        self.skip_btn.config(state=tk.DISABLED)
        self.update_status_label.config(
            text=f"已设置为不再提醒版本 {self.latest_version}", fg="#fa8c16"
        )

    def _on_skip_updates_changed(self):
        """不接收更新提醒复选框变化回调"""
        enabled = self.skip_updates_var.get()
        config = load_config()
        config["skip_updates"] = enabled
        save_config(config)
        if enabled:
            self.update_status_label.config(text="已关闭更新提醒", fg="#fa8c16")
        else:
            self.update_status_label.config(text="已开启更新提醒", fg="#52c41a")


def show_settings_dialog(parent, app, version):
    """显示设置对话框的便捷函数"""
    settings = SettingsWindow(parent, app, version)
    settings.show()
