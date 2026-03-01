"""音乐播放器标签页"""

import random
import tkinter as tk

from ..config import load_config, save_config


def create_music_tab(settings_window, parent):
    """创建音乐播放器标签页 - 歌姬偶像风格

    Args:
        settings_window: SettingsWindow 实例
        parent: 父容器

    Returns:
        创建的标签页 frame
    """
    frame = tk.Frame(parent, bg=settings_window.colors["bg"])

    # 创建内嵌音乐播放器（使用统一风格）
    settings_window.music_player_embedded = MusicPlayerEmbedded(
        frame, settings_window.colors, settings_window.fonts
    )

    return frame


class MusicPlayerEmbedded:
    """内嵌音乐播放器 - 歌姬偶像风格"""

    def __init__(self, parent, colors, fonts):
        self.parent = parent
        self.colors = colors
        self.fonts = fonts
        self.config = load_config()

        # 创建实际的播放器核心（使用 MusicPlayer 的音频功能）
        from ..music_player import MusicPlayer

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
            height=8,
            width=45,
        )
        self.listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        scrollbar.config(command=self.listbox.yview)

        self.listbox.bind("<Double-Button-1>", self._on_double_click)

        # 获取用户音乐文件夹路径（首次运行复制自带歌曲）
        self.music_folder = self._get_user_music_folder()

        # 可点击的文件夹路径标签
        folder_label = tk.Label(
            playlist_frame,
            text=f"📁 打开歌曲文件夹: {self.music_folder}",
            font=self.fonts["small"],
            bg=self.colors["card_bg"],
            fg=self.colors["accent"],
            cursor="hand2",
        )
        folder_label.pack(pady=(5, 0))
        folder_label.bind("<Button-1>", lambda e: self._open_music_folder())

        # 刷新按钮
        refresh_btn = tk.Label(
            playlist_frame,
            text="🔄 点击刷新歌曲列表",
            font=self.fonts["small"],
            bg=self.colors["card_bg"],
            fg=self.colors["subtext"],
            cursor="hand2",
        )
        refresh_btn.pack(pady=(3, 0))
        refresh_btn.bind("<Button-1>", lambda e: self._refresh_list())

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

        # 保存按钮引用（空列表，因为已删除按钮）
        self.action_buttons = []

    def _get_user_music_folder(self):
        """获取用户音乐文件夹路径，首次运行复制自带歌曲"""
        import os
        import shutil
        from ..utils import resource_path

        music_folder = os.path.join(os.path.expanduser("~"), "ameath_songs")

        # 如果文件夹不存在，创建它
        if not os.path.exists(music_folder):
            os.makedirs(music_folder, exist_ok=True)

            # 首次运行，复制自带歌曲（使用 resource_path 获取打包后的路径）
            bundled_music = resource_path("sound/music")
            if os.path.exists(bundled_music):
                for file in os.listdir(bundled_music):
                    if file.lower().endswith((".wav", ".mp3")):
                        src = os.path.join(bundled_music, file)
                        dst = os.path.join(music_folder, file)
                        shutil.copy2(src, dst)

        return music_folder

    def _open_music_folder(self):
        """打开音乐文件夹"""
        import os
        import subprocess

        try:
            subprocess.Popen(f'explorer "{self.music_folder}"', shell=True)
        except Exception as e:
            print(f"打开文件夹失败: {e}")

    def _load_music_files(self):
        """加载音乐文件列表"""
        import os

        # 使用用户音乐文件夹
        music_dir = self.music_folder
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
        # 调用apply_current_volume同步到共享变量，确保音频回调读取最新值
        self.core_player.apply_current_volume()

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
        if not self.music_files:
            return
        
        # 如果没有选中歌曲，随机选择一首
        if self.current_index < 0:
            self.current_index = random.randint(0, len(self.music_files) - 1)
            self._update_listbox()

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
        from ..utils import resource_path

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
