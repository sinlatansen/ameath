"""检查更新标签页"""

import tkinter as tk
from tkinter import ttk
import threading

from ..config import load_config, save_config
from ..utils import check_update


def create_update_tab(settings_window, parent):
    """创建检查更新标签页

    Args:
        settings_window: SettingsWindow 实例
        parent: 父容器

    Returns:
        创建的标签页 frame
    """
    frame = ttk.Frame(parent, padding=20)
    frame.columnconfigure(0, weight=1)

    # 加载当前配置
    config = load_config()
    current_skip_updates = config.get("skip_updates", False)

    # 当前版本信息
    version_frame = tk.Frame(frame, bg=settings_window.colors["bg"])
    version_frame.grid(row=0, column=0, sticky="ew", pady=(0, 15))

    tk.Label(
        version_frame,
        text=f"当前版本: {settings_window.version}",
        font=settings_window.fonts["title"],
        fg=settings_window.colors["accent_dark"],
        bg=settings_window.colors["bg"],
    ).pack(anchor=tk.W)

    # 分隔线
    separator = ttk.Separator(frame, orient="horizontal")
    separator.grid(row=1, column=0, sticky="ew", pady=12)

    # 检查更新按钮
    settings_window.check_btn = tk.Button(
        frame,
        text="检查更新",
        command=settings_window._on_check_update,
        font=settings_window.fonts["subtitle"],
        width=14,
        bg=settings_window.colors["accent"],
        fg="white",
        activebackground=settings_window.colors["accent_dark"],
        activeforeground="white",
        relief=tk.FLAT,
        bd=0,
        cursor="hand2",
    )
    settings_window.check_btn.grid(row=2, column=0, pady=10)

    # 状态标签
    settings_window.update_status_label = tk.Label(
        frame,
        text="点击上方按钮检查是否有新版本可用",
        font=settings_window.fonts["base"],
        fg=settings_window.colors["subtext"],
        bg=settings_window.colors["bg"],
    )
    settings_window.update_status_label.grid(row=3, column=0, pady=8)

    # 分隔线
    separator2 = ttk.Separator(frame, orient="horizontal")
    separator2.grid(row=4, column=0, sticky="ew", pady=12)

    # 更新信息区域
    info_container = tk.Frame(frame, bg=settings_window.colors["bg"])
    info_container.grid(row=5, column=0, sticky="nsew", pady=5)
    frame.rowconfigure(5, weight=1)

    # 最新版本标签
    settings_window.latest_version_label = tk.Label(
        info_container,
        text="",
        font=settings_window.fonts["subtitle"],
        fg=settings_window.colors["accent_dark"],
        bg=settings_window.colors["bg"],
        anchor=tk.W,
    )
    settings_window.latest_version_label.pack(fill=tk.X, pady=(0, 8))

    # 发布说明标签
    tk.Label(
        info_container,
        text="发布说明:",
        font=settings_window.fonts["base"],
        fg=settings_window.colors["accent_dark"],
        bg=settings_window.colors["bg"],
        anchor=tk.W,
    ).pack(fill=tk.X, pady=(0, 5))

    # 发布说明文本框（带边框和滚动条）
    text_frame = tk.Frame(
        info_container,
        bd=1,
        relief=tk.SOLID,
        bg=settings_window.colors["border"],
    )
    text_frame.pack(fill=tk.BOTH, expand=True)

    settings_window.release_notes_text = tk.Text(
        text_frame,
        height=9,
        wrap=tk.WORD,
        font=settings_window.fonts["base"],
        state=tk.DISABLED,
        padx=10,
        pady=10,
        relief=tk.FLAT,
        bg=settings_window.colors["card_bg"],
        fg=settings_window.colors["text"],
        insertbackground=settings_window.colors["accent_dark"],
    )
    settings_window.release_notes_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # 滚动条
    scrollbar = tk.Scrollbar(
        text_frame,
        command=settings_window.release_notes_text.yview,
        width=14,
        bg=settings_window.colors["tab_bg"],
        activebackground=settings_window.colors["tab_active"],
        troughcolor=settings_window.colors["card_bg"],
    )
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    settings_window.release_notes_text.config(yscrollcommand=scrollbar.set)

    # 操作按钮区域
    settings_window.update_btn_frame = tk.Frame(frame, bg=settings_window.colors["bg"])
    settings_window.update_btn_frame.grid(row=6, column=0, sticky="ew", pady=(12, 0))

    # 下载和跳过按钮
    button_left = tk.Frame(
        settings_window.update_btn_frame, bg=settings_window.colors["bg"]
    )
    button_left.pack(side=tk.LEFT)

    settings_window.download_btn = tk.Button(
        button_left,
        text="下载并更新",
        command=settings_window._on_download_update,
        font=settings_window.fonts["base"],
        width=12,
        bg=settings_window.colors["accent"],
        fg="white",
        activebackground=settings_window.colors["accent_dark"],
        activeforeground="white",
        state=tk.DISABLED,
        relief=tk.FLAT,
        bd=0,
        cursor="hand2",
    )
    settings_window.download_btn.pack(side=tk.LEFT, padx=(0, 10))

    settings_window.skip_btn = tk.Button(
        button_left,
        text="跳过此版本",
        command=settings_window._on_skip_version,
        font=settings_window.fonts["base"],
        width=12,
        bg=settings_window.colors["tab_bg"],
        fg=settings_window.colors["accent_dark"],
        activebackground=settings_window.colors["tab_active"],
        activeforeground=settings_window.colors["accent_dark"],
        relief=tk.FLAT,
        bd=0,
        state=tk.DISABLED,
        cursor="hand2",
    )
    settings_window.skip_btn.pack(side=tk.LEFT)

    # 不接收更新提醒复选框（右侧）
    settings_window.skip_updates_var = tk.BooleanVar(value=current_skip_updates)
    skip_updates_cb = tk.Checkbutton(
        settings_window.update_btn_frame,
        text="不接收更新提醒",
        variable=settings_window.skip_updates_var,
        font=settings_window.fonts["control"],
        bg=settings_window.colors["bg"],
        fg=settings_window.colors["text"],
        activebackground=settings_window.colors["bg"],
        activeforeground=settings_window.colors["accent_dark"],
        selectcolor=settings_window.colors["bg"],
        command=settings_window._on_skip_updates_changed,
    )
    skip_updates_cb.pack(side=tk.RIGHT)

    return frame


# ===== 检查更新回调函数 =====


def setup_update_callbacks(SettingsWindow):
    """为 SettingsWindow 类添加检查更新的回调方法"""

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
        """执行下载更新（在后台线程）"""
        try:
            from ..utils import download_and_update

            result = download_and_update(
                self._latest_asset_url, self._latest_asset_name
            )
            if self.window and self.window.winfo_exists():
                self.window.after(0, lambda: self._on_download_result(result))
        except Exception as e:
            if self.window and self.window.winfo_exists():
                self.window.after(0, lambda: self._on_download_error(str(e)))

    def _on_download_result(self, result):
        """下载更新结果回调"""
        self.check_btn.config(state=tk.NORMAL)
        if result:
            self.update_status_label.config(
                text="下载完成，将自动安装并重启", fg=self.colors["accent"]
            )
            self.window.after(2000, self._on_close)
        else:
            self.update_status_label.config(text="下载失败，请稍后重试", fg="#D24B4B")
            self.download_btn.config(state=tk.NORMAL)
            self.skip_btn.config(state=tk.NORMAL)

    def _on_download_error(self, error_msg):
        """下载更新错误回调"""
        self.check_btn.config(state=tk.NORMAL)
        self.update_status_label.config(text=f"下载失败: {error_msg}", fg="#D24B4B")
        self.download_btn.config(state=tk.NORMAL)
        self.skip_btn.config(state=tk.NORMAL)

    def _on_update_error(self, error_msg):
        """检查更新错误回调"""
        self.check_btn.config(state=tk.NORMAL)
        self.update_status_label.config(text=f"检查更新失败: {error_msg}", fg="#D24B4B")

    def _on_skip_version(self):
        """跳过此版本"""
        self.update_status_label.config(text="已跳过此版本", fg=self.colors["subtext"])
        self.download_btn.config(state=tk.DISABLED)
        self.skip_btn.config(state=tk.DISABLED)
        self.latest_version = None
        self._latest_asset_url = None
        self._latest_asset_name = None

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

    # 将方法绑定到类
    SettingsWindow._on_check_update = _on_check_update
    SettingsWindow._do_check_update = _do_check_update
    SettingsWindow._on_update_result = _on_update_result
    SettingsWindow._on_download_update = _on_download_update
    SettingsWindow._do_download_update = _do_download_update
    SettingsWindow._on_download_result = _on_download_result
    SettingsWindow._on_download_error = _on_download_error
    SettingsWindow._on_update_error = _on_update_error
    SettingsWindow._on_skip_version = _on_skip_version
    SettingsWindow._on_skip_updates_changed = _on_skip_updates_changed
