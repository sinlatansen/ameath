"""个性化设置标签页"""

import tkinter as tk
from tkinter import ttk, messagebox

from ..config import load_config, save_config
from ..constants import (
    SCREEN_INDEX,
    SCALE_OPTIONS,
    TRANSPARENCY_OPTIONS,
    DEFAULT_SCREEN_INDEX,
    DEFAULT_SCALE_INDEX,
    DEFAULT_TRANSPARENCY_INDEX,
    DEFAULT_WANDER_IDLE_STAY_MODE,
    DEFAULT_VOICE_ENABLED,
    DEFAULT_VOICE_VOLUME,
)


def create_personalization_tab(settings_window, parent):
    """创建个性化标签页

    Args:
        settings_window: SettingsWindow 实例
        parent: 父容器

    Returns:
        创建的标签页 frame
    """
    frame = ttk.Frame(parent)
    canvas = tk.Canvas(
        frame,
        bg=settings_window.colors["bg"],
        highlightthickness=0,
        bd=0,
    )
    scrollbar = tk.Scrollbar(
        frame,
        orient=tk.VERTICAL,
        command=canvas.yview,
        width=12,
        bg=settings_window.colors["tab_bg"],
        activebackground=settings_window.colors["tab_active"],
        troughcolor=settings_window.colors["card_bg"],
    )
    canvas.configure(yscrollcommand=scrollbar.set)

    content = tk.Frame(canvas, bg=settings_window.colors["bg"])
    inner_frame = tk.Frame(content, bg=settings_window.colors["bg"])
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
        font=settings_window.fonts["subtitle"],
        padx=15,
        pady=12,
        bg=settings_window.colors["card_bg"],
        fg=settings_window.colors["accent_dark"],
        bd=1,
        relief=tk.SOLID,
    )
    scale_frame.pack(fill=tk.X, pady=(0, 15), ipady=5)

    settings_window.scale_var = tk.IntVar(value=current_scale_idx)

    # 使用网格布局，多列展示
    scale_grid = tk.Frame(scale_frame, bg=settings_window.colors["card_bg"])
    scale_grid.pack(fill=tk.X, pady=5)

    scale_columns = 5
    for i, scale_val in enumerate(SCALE_OPTIONS):
        row = i // scale_columns
        col = i % scale_columns
        rb = tk.Radiobutton(
            scale_grid,
            text=f"{scale_val}x",
            variable=settings_window.scale_var,
            value=i,
            font=settings_window.fonts["control"],
            bg=settings_window.colors["card_bg"],
            fg=settings_window.colors["text"],
            activebackground=settings_window.colors["card_bg"],
            activeforeground=settings_window.colors["accent_dark"],
            selectcolor=settings_window.colors["bg"],
            command=settings_window._on_scale_changed,
            anchor=tk.W,
        )
        rb.grid(row=row, column=col, sticky=tk.W, padx=15, pady=6)

    # ===== 透明度设置 =====
    trans_frame = tk.LabelFrame(
        inner_frame,
        text="窗口透明度",
        font=settings_window.fonts["subtitle"],
        padx=15,
        pady=12,
        bg=settings_window.colors["card_bg"],
        fg=settings_window.colors["accent_dark"],
        bd=1,
        relief=tk.SOLID,
    )
    trans_frame.pack(fill=tk.X, pady=(0, 15), ipady=5)

    settings_window.transparency_var = tk.IntVar(value=current_transparency_idx)

    # 使用网格布局，多列展示
    trans_grid = tk.Frame(trans_frame, bg=settings_window.colors["card_bg"])
    trans_grid.pack(fill=tk.X, pady=5)

    trans_columns = 5
    for i, trans_val in enumerate(TRANSPARENCY_OPTIONS):
        row = i // trans_columns
        col = i % trans_columns
        rb = tk.Radiobutton(
            trans_grid,
            text=f"{int(trans_val * 100)}%",
            variable=settings_window.transparency_var,
            value=i,
            font=settings_window.fonts["control"],
            bg=settings_window.colors["card_bg"],
            fg=settings_window.colors["text"],
            activebackground=settings_window.colors["card_bg"],
            activeforeground=settings_window.colors["accent_dark"],
            selectcolor=settings_window.colors["bg"],
            command=settings_window._on_transparency_changed,
            anchor=tk.W,
        )
        rb.grid(row=row, column=col, sticky=tk.W, padx=20, pady=6)

    # ===== 开机自启设置 =====
    startup_frame = tk.LabelFrame(
        inner_frame,
        text="启动选项",
        font=settings_window.fonts["subtitle"],
        padx=15,
        pady=12,
        bg=settings_window.colors["card_bg"],
        fg=settings_window.colors["accent_dark"],
        bd=1,
        relief=tk.SOLID,
    )
    startup_frame.pack(fill=tk.X, pady=(0, 10), ipady=5)

    settings_window.auto_startup_var = tk.BooleanVar(value=current_auto_startup)
    startup_cb = tk.Checkbutton(
        startup_frame,
        text="开机时自动启动程序",
        variable=settings_window.auto_startup_var,
        font=settings_window.fonts["control"],
        bg=settings_window.colors["card_bg"],
        fg=settings_window.colors["text"],
        activebackground=settings_window.colors["card_bg"],
        activeforeground=settings_window.colors["accent_dark"],
        selectcolor=settings_window.colors["bg"],
        command=settings_window._on_startup_changed,
        anchor=tk.W,
    )
    startup_cb.pack(anchor=tk.W, pady=3)

    # 添加说明文字
    tk.Label(
        startup_frame,
        text="开启后，系统启动时将自动运行桌面宠物",
        font=settings_window.fonts["small"],
        fg=settings_window.colors["subtext"],
        bg=settings_window.colors["card_bg"],
        anchor=tk.W,
    ).pack(anchor=tk.W, padx=22)

    # ===== 语音设置 =====
    voice_frame = tk.LabelFrame(
        inner_frame,
        text="语音设置",
        font=settings_window.fonts["subtitle"],
        padx=15,
        pady=12,
        bg=settings_window.colors["card_bg"],
        fg=settings_window.colors["accent_dark"],
        bd=1,
        relief=tk.SOLID,
    )
    voice_frame.pack(fill=tk.X, pady=(0, 10), ipady=5)

    # 语音开关
    settings_window.voice_enabled_var = tk.BooleanVar(value=current_voice_enabled)
    voice_enabled_cb = tk.Checkbutton(
        voice_frame,
        text="启用点击音效",
        variable=settings_window.voice_enabled_var,
        font=settings_window.fonts["control"],
        bg=settings_window.colors["card_bg"],
        fg=settings_window.colors["text"],
        activebackground=settings_window.colors["card_bg"],
        activeforeground=settings_window.colors["accent_dark"],
        selectcolor=settings_window.colors["bg"],
        command=settings_window._on_voice_enabled_changed,
        anchor=tk.W,
    )
    voice_enabled_cb.pack(anchor=tk.W, pady=3)

    # 音量滑块
    volume_row = tk.Frame(voice_frame, bg=settings_window.colors["card_bg"])
    volume_row.pack(fill=tk.X, pady=(8, 3), padx=22)

    tk.Label(
        volume_row,
        text="音量: ",
        font=settings_window.fonts["control"],
        bg=settings_window.colors["card_bg"],
        fg=settings_window.colors["text"],
    ).pack(side=tk.LEFT)

    settings_window.voice_volume_var = tk.IntVar(value=current_voice_volume)
    settings_window.voice_volume_scale = tk.Scale(
        volume_row,
        from_=0,
        to=150,
        orient=tk.HORIZONTAL,
        variable=settings_window.voice_volume_var,
        length=200,
        font=settings_window.fonts["small"],
        bg=settings_window.colors["card_bg"],
        fg=settings_window.colors["text"],
        highlightthickness=0,
        troughcolor=settings_window.colors["tab_bg"],
        activebackground=settings_window.colors["accent"],
        command=settings_window._on_voice_volume_changed,
    )
    settings_window.voice_volume_scale.pack(side=tk.LEFT, padx=(5, 10))

    settings_window.voice_volume_label = tk.Label(
        volume_row,
        text=f"{current_voice_volume}%",
        font=settings_window.fonts["control"],
        bg=settings_window.colors["card_bg"],
        fg=settings_window.colors["accent_dark"],
        width=5,
    )
    settings_window.voice_volume_label.pack(side=tk.LEFT)

    # 说明文字
    tk.Label(
        voice_frame,
        text="拖动桌宠时播放随机音效，音量可随时调整",
        font=settings_window.fonts["small"],
        fg=settings_window.colors["subtext"],
        bg=settings_window.colors["card_bg"],
        anchor=tk.W,
    ).pack(anchor=tk.W, padx=22)

    # ===== 音乐播放器设置 =====
    music_frame = tk.LabelFrame(
        inner_frame,
        text="音乐播放器",
        font=settings_window.fonts["subtitle"],
        padx=15,
        pady=12,
        bg=settings_window.colors["card_bg"],
        fg=settings_window.colors["accent_dark"],
        bd=1,
        relief=tk.SOLID,
    )
    music_frame.pack(fill=tk.X, pady=(0, 10), ipady=5)

    # 音乐播放器开关
    settings_window.music_enabled_var = tk.BooleanVar(
        value=config.get("music_enabled", False)
    )
    music_enabled_cb = tk.Checkbutton(
        music_frame,
        text="启用右键音乐播放器",
        variable=settings_window.music_enabled_var,
        font=settings_window.fonts["control"],
        bg=settings_window.colors["card_bg"],
        fg=settings_window.colors["text"],
        activebackground=settings_window.colors["card_bg"],
        activeforeground=settings_window.colors["accent_dark"],
        selectcolor=settings_window.colors["bg"],
        command=settings_window._on_music_enabled_changed,
        anchor=tk.W,
    )
    music_enabled_cb.pack(anchor=tk.W, pady=3)

    # 音乐音量滑块
    music_volume_row = tk.Frame(music_frame, bg=settings_window.colors["card_bg"])
    music_volume_row.pack(fill=tk.X, pady=(8, 3), padx=22)

    tk.Label(
        music_volume_row,
        text="音乐音量: ",
        font=settings_window.fonts["control"],
        bg=settings_window.colors["card_bg"],
        fg=settings_window.colors["text"],
    ).pack(side=tk.LEFT)

    settings_window.music_volume_var = tk.IntVar(value=config.get("music_volume", 100))
    settings_window.music_volume_scale = tk.Scale(
        music_volume_row,
        from_=0,
        to=100,
        orient=tk.HORIZONTAL,
        variable=settings_window.music_volume_var,
        length=200,
        font=settings_window.fonts["small"],
        bg=settings_window.colors["card_bg"],
        fg=settings_window.colors["text"],
        highlightthickness=0,
        troughcolor=settings_window.colors["tab_bg"],
        activebackground=settings_window.colors["accent"],
        command=settings_window._on_music_volume_changed,
    )
    settings_window.music_volume_scale.pack(side=tk.LEFT, padx=(5, 10))

    settings_window.music_volume_label = tk.Label(
        music_volume_row,
        text=f"{config.get('music_volume', 100)}%",
        font=settings_window.fonts["control"],
        bg=settings_window.colors["card_bg"],
        fg=settings_window.colors["accent_dark"],
        width=5,
    )
    settings_window.music_volume_label.pack(side=tk.LEFT)

    # 说明文字
    tk.Label(
        music_frame,
        text="右键点击桌宠打开音乐播放器",
        font=settings_window.fonts["small"],
        fg=settings_window.colors["subtext"],
        bg=settings_window.colors["card_bg"],
        anchor=tk.W,
    ).pack(anchor=tk.W, padx=22)

    # ===== 屏幕设置 =====
    screen_frame = tk.LabelFrame(
        inner_frame,
        text="屏幕设置",
        font=settings_window.fonts["subtitle"],
        padx=15,
        pady=12,
        bg=settings_window.colors["card_bg"],
        fg=settings_window.colors["accent_dark"],
        bd=1,
        relief=tk.SOLID,
    )
    screen_frame.pack(fill=tk.X, pady=(0, 10), ipady=5)

    tk.Label(
        screen_frame,
        text="提示：更改后需重启软件生效",
        font=settings_window.fonts["small"],
        fg=settings_window.colors["subtext"],
        bg=settings_window.colors["card_bg"],
        anchor=tk.W,
    ).pack(anchor=tk.W, padx=2, pady=(6, 10))

    # 模式选择：固定屏幕 / 跨屏游荡
    settings_window.display_mode_var = tk.StringVar(
        value="wander" if current_total_screen else "fixed"
    )

    # 固定屏幕选项（包含屏幕选择器）
    fixed_frame = tk.Frame(screen_frame, bg=settings_window.colors["card_bg"])
    fixed_frame.pack(fill=tk.X, pady=(0, 5))

    fixed_rb = tk.Radiobutton(
        fixed_frame,
        text="固定屏幕",
        variable=settings_window.display_mode_var,
        value="fixed",
        font=settings_window.fonts["control"],
        bg=settings_window.colors["card_bg"],
        fg=settings_window.colors["text"],
        activebackground=settings_window.colors["card_bg"],
        activeforeground=settings_window.colors["accent_dark"],
        selectcolor=settings_window.colors["bg"],
        command=settings_window._on_display_mode_changed,
        anchor=tk.W,
    )
    fixed_rb.pack(side=tk.LEFT)

    # 屏幕选择器（紧随RadioButton之后）
    settings_window.screen_select_container = tk.Frame(
        fixed_frame, bg=settings_window.colors["card_bg"]
    )
    settings_window.screen_select_container.pack(side=tk.LEFT, padx=(10, 0))

    # 屏幕选项
    settings_window.screen_var = tk.IntVar(value=current_screen_idx)
    screen_grid = tk.Frame(
        settings_window.screen_select_container, bg=settings_window.colors["card_bg"]
    )
    screen_grid.pack(fill=tk.X)

    screen_columns = 5
    for i, screen_val in enumerate(SCREEN_INDEX):
        row = i // screen_columns
        col = i % screen_columns
        rb = tk.Radiobutton(
            screen_grid,
            text=f"屏幕{int(screen_val) + 1}",
            variable=settings_window.screen_var,
            value=i,
            font=settings_window.fonts["base"],
            bg=settings_window.colors["card_bg"],
            fg=settings_window.colors["text"],
            activebackground=settings_window.colors["card_bg"],
            activeforeground=settings_window.colors["accent_dark"],
            selectcolor=settings_window.colors["bg"],
            command=settings_window._on_screen_changed,
            anchor=tk.W,
        )
        rb.grid(row=row, column=col, sticky=tk.W, padx=10, pady=3)

    # 跨屏游荡选项
    wander_frame = tk.Frame(screen_frame, bg=settings_window.colors["card_bg"])
    wander_frame.pack(fill=tk.X, pady=(10, 0))

    wander_rb = tk.Radiobutton(
        wander_frame,
        text="跨屏游荡",
        variable=settings_window.display_mode_var,
        value="wander",
        font=settings_window.fonts["control"],
        bg=settings_window.colors["card_bg"],
        fg=settings_window.colors["text"],
        activebackground=settings_window.colors["card_bg"],
        activeforeground=settings_window.colors["accent_dark"],
        selectcolor=settings_window.colors["bg"],
        command=settings_window._on_display_mode_changed,
        anchor=tk.W,
    )
    wander_rb.pack(side=tk.LEFT)

    # 提示文字
    tk.Label(
        wander_frame,
        text="（在多个屏幕间自由移动，强烈建议开启鼠标跟随）",
        font=settings_window.fonts["small"],
        fg=settings_window.colors["subtext"],
        bg=settings_window.colors["card_bg"],
        anchor=tk.W,
    ).pack(side=tk.LEFT, padx=(5, 0))

    # 根据当前模式更新UI状态
    settings_window._update_screen_options_visibility()

    # ===== 显示优先级设置 =====
    priority_frame = tk.LabelFrame(
        inner_frame,
        text="显示优先级",
        font=settings_window.fonts["subtitle"],
        padx=15,
        pady=12,
        bg=settings_window.colors["card_bg"],
        fg=settings_window.colors["accent_dark"],
        bd=1,
        relief=tk.SOLID,
    )
    priority_frame.pack(fill=tk.X, pady=(0, 10), ipady=5)

    settings_window.display_priority_var = tk.IntVar(value=current_display_priority)
    priority_options = [
        ("始终置顶", 1),
        ("全屏时隐藏", 2),
        ("仅在桌面显示", 3),
    ]
    for text, value in priority_options:
        rb = tk.Radiobutton(
            priority_frame,
            text=text,
            variable=settings_window.display_priority_var,
            value=value,
            font=settings_window.fonts["control"],
            bg=settings_window.colors["card_bg"],
            fg=settings_window.colors["text"],
            activebackground=settings_window.colors["card_bg"],
            activeforeground=settings_window.colors["accent_dark"],
            selectcolor=settings_window.colors["bg"],
            command=settings_window._on_display_priority_changed,
            anchor=tk.W,
        )
        rb.pack(anchor=tk.W, pady=2)

    tk.Label(
        priority_frame,
        text="仅在桌面显示：打开应用窗口时会被覆盖",
        font=settings_window.fonts["small"],
        fg=settings_window.colors["subtext"],
        bg=settings_window.colors["card_bg"],
        anchor=tk.W,
    ).pack(anchor=tk.W, padx=22, pady=(6, 0))

    # ===== 多开模式 =====
    multi_frame = tk.LabelFrame(
        inner_frame,
        text="多开模式",
        font=settings_window.fonts["subtitle"],
        padx=15,
        pady=12,
        bg=settings_window.colors["card_bg"],
        fg=settings_window.colors["accent_dark"],
        bd=1,
        relief=tk.SOLID,
    )
    multi_frame.pack(fill=tk.X, pady=(0, 10), ipady=5)

    multi_row = tk.Frame(multi_frame, bg=settings_window.colors["card_bg"])
    multi_row.pack(anchor=tk.W, pady=4)

    tk.Label(
        multi_row,
        text="实例数量:",
        font=settings_window.fonts["control"],
        bg=settings_window.colors["card_bg"],
        fg=settings_window.colors["text"],
    ).pack(side=tk.LEFT)

    settings_window.instance_count_var = tk.StringVar(value=str(current_instance_count))
    settings_window.instance_count_entry = tk.Entry(
        multi_row,
        textvariable=settings_window.instance_count_var,
        width=6,
        font=settings_window.fonts["control"],
        bg=settings_window.colors["bg"],
        fg=settings_window.colors["text"],
        relief=tk.FLAT,
        highlightthickness=1,
        highlightbackground=settings_window.colors["border"],
        highlightcolor=settings_window.colors["accent"],
    )
    settings_window.instance_count_entry.pack(side=tk.LEFT, padx=(8, 8))

    tk.Button(
        multi_row,
        text="确定",
        command=settings_window._on_instance_count_confirm,
        font=settings_window.fonts["base"],
        width=6,
        bg=settings_window.colors["accent"],
        fg="white",
        activebackground=settings_window.colors["accent_dark"],
        activeforeground="white",
        relief=tk.FLAT,
        bd=0,
        cursor="hand2",
    ).pack(side=tk.LEFT)

    tk.Label(
        multi_frame,
        text="警告：请根据自身电脑性能，量力而行，最多80个。",
        font=settings_window.fonts["small"],
        fg=settings_window.colors["subtext"],
        bg=settings_window.colors["card_bg"],
        anchor=tk.W,
    ).pack(anchor=tk.W, padx=2, pady=(6, 0))

    tk.Label(
        multi_frame,
        text="超过10个时，在此界面会暂停桌宠们。",
        font=settings_window.fonts["small"],
        fg=settings_window.colors["subtext"],
        bg=settings_window.colors["card_bg"],
        anchor=tk.W,
    ).pack(anchor=tk.W, padx=2, pady=(6, 0))

    tk.Label(
        multi_frame,
        text=(f"如果设置太多导致软件崩溃无法启动"),
        font=settings_window.fonts["small"],
        fg=settings_window.colors["subtext"],
        bg=settings_window.colors["card_bg"],
        anchor=tk.W,
    ).pack(anchor=tk.W, padx=2, pady=(2, 0))

    import getpass

    username = getpass.getuser()

    tk.Label(
        multi_frame,
        text=(f"请'win+R'打开运行，输入'%appdata%/ameath_config.json'打开配置文件"),
        font=settings_window.fonts["small"],
        fg=settings_window.colors["subtext"],
        bg=settings_window.colors["card_bg"],
        anchor=tk.W,
    ).pack(anchor=tk.W, padx=2, pady=(2, 0))

    tk.Label(
        multi_frame,
        text=(f"手动修改 instance_count 参数为1。"),
        font=settings_window.fonts["small"],
        fg=settings_window.colors["subtext"],
        bg=settings_window.colors["card_bg"],
        anchor=tk.W,
    ).pack(anchor=tk.W, padx=2, pady=(2, 0))

    # ===== 游荡停驻设置 =====
    wander_idle_frame = tk.LabelFrame(
        inner_frame,
        text="游荡模式下是否停驻播放idle动作",
        font=settings_window.fonts["subtitle"],
        padx=15,
        pady=12,
        bg=settings_window.colors["card_bg"],
        fg=settings_window.colors["accent_dark"],
        bd=1,
        relief=tk.SOLID,
    )
    wander_idle_frame.pack(fill=tk.X, pady=(0, 10), ipady=5)

    settings_window.wander_idle_stay_mode_var = tk.IntVar(
        value=current_wander_idle_stay_mode
    )
    wander_idle_options = [
        ("始终移动", 0),
        ("概率停驻", 1),
        ("停驻", 2),
    ]
    for text, value in wander_idle_options:
        rb = tk.Radiobutton(
            wander_idle_frame,
            text=text,
            variable=settings_window.wander_idle_stay_mode_var,
            value=value,
            font=settings_window.fonts["control"],
            bg=settings_window.colors["card_bg"],
            fg=settings_window.colors["text"],
            activebackground=settings_window.colors["card_bg"],
            activeforeground=settings_window.colors["accent_dark"],
            selectcolor=settings_window.colors["bg"],
            command=settings_window._on_wander_idle_stay_mode_changed,
            anchor=tk.W,
        )
        rb.pack(anchor=tk.W, pady=2)

    return frame


# ===== 个性化设置回调函数 =====


def setup_personalization_callbacks(SettingsWindow):
    """为 SettingsWindow 类添加个性化设置的回调方法"""

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
        from ..config import set_auto_startup

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

    # 将方法绑定到类
    SettingsWindow._on_scale_changed = _on_scale_changed
    SettingsWindow._on_transparency_changed = _on_transparency_changed
    SettingsWindow._on_startup_changed = _on_startup_changed
    SettingsWindow._on_voice_enabled_changed = _on_voice_enabled_changed
    SettingsWindow._on_voice_volume_changed = _on_voice_volume_changed
    SettingsWindow._on_music_enabled_changed = _on_music_enabled_changed
    SettingsWindow._on_music_volume_changed = _on_music_volume_changed
    SettingsWindow._on_display_mode_changed = _on_display_mode_changed
    SettingsWindow._update_screen_options_visibility = _update_screen_options_visibility
    SettingsWindow._set_screen_select_state = _set_screen_select_state
    SettingsWindow._on_screen_changed = _on_screen_changed
    SettingsWindow._on_display_priority_changed = _on_display_priority_changed
    SettingsWindow._on_wander_idle_stay_mode_changed = _on_wander_idle_stay_mode_changed
    SettingsWindow._on_instance_count_confirm = _on_instance_count_confirm
