import os
import sys
import threading
import queue
import wave
import numpy as np
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sounddevice as sd
from .config import load_config, save_config
from .utils import resource_path
import time

MUSIC_DIR = os.path.join(os.path.expanduser("~"), "ameath_songs")


class MusicPlayer:
    """音乐播放器类 - 支持后台播放和恢复"""

    # 类变量，用于在GUI关闭后保持状态
    _instance = None
    _shared_audio_data = None
    _shared_sample_rate = None
    _shared_channels = None
    _shared_total_length = 0
    _shared_current_position = 0
    _shared_current_index = -1
    _shared_is_playing = False
    _shared_is_paused = False
    _shared_thread = None
    _shared_stop_event = None
    _shared_pause_event = None
    _shared_queue = None
    _shared_stream = None
    _shared_music_files = []
    _shared_song_name = "未选择歌曲"

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, parent=None, position_unlock_callback=None, colors=None):
        # 如果是重复初始化（parent为None表示只更新状态）
        if parent is None:
            return

        # 检查是否已经初始化过
        if hasattr(self, "_initialized") and self._initialized:
            # 更新GUI引用
            self.parent = parent
            self.position_unlock_callback = position_unlock_callback
            self._sync_from_shared()
            self.create_gui()
            return

        self._initialized = True

        self.parent = parent
        self.position_unlock_callback = position_unlock_callback
        self.music_files = []
        self.current_index = -1
        self.is_playing = False
        self.is_paused = False
        self.playback_thread = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.current_position = 0
        self.total_length = 0
        self.audio_data = None
        self.sample_rate = None
        self.channels = None
        self.paused_position = 0
        self.current_song_name = "未选择歌曲"

        # 音频队列
        self.audio_queue = queue.Queue(maxsize=10)
        self.stream = None

        # GUI元素引用（用于检查是否存在）
        self.listbox = None
        self.current_song_label = None
        self.progress_var = None
        self.progress_bar = None
        self.time_label = None
        self.play_pause_btn = None
        self.volume_scale = None
        self.volume_var = None

        # 主题颜色（支持外部传入）
        if colors:
            # 使用外部传入的颜色（设置窗口风格）
            self.pink_light = colors.get("bg", "#FFF1F6")
            self.blue_sky = colors.get("card_bg", "#FFFFFF")
            self.white = colors.get("card_bg", "#FFFFFF")
            self.text_dark = colors.get("text", "#4A2A3A")
            self.text_light = colors.get("subtext", "#7A5564")
            self.accent_color = colors.get("accent", "#FF69B4")
            self.accent_dark = colors.get("accent_dark", "#E84D8E")
            self.border_color = colors.get("border", "#F3C2D4")
            self.tab_bg = colors.get("tab_bg", "#FFE1EE")
        else:
            # 默认颜色（独立窗口风格）
            self.pink_light = "#FFD1DC"
            self.blue_sky = "#E6F3FF"
            self.white = "#FFFFFF"
            self.text_dark = "#333333"
            self.text_light = "#666666"
            self.accent_color = "#FF69B4"
            self.accent_dark = "#E84D8E"
            self.border_color = "#F3C2D4"
            self.tab_bg = "#FFE1EE"

        # 加载配置
        config = load_config()
        self.music_volume = config.get("music_volume", 100)

        # 先加载文件列表（不依赖GUI）
        self.load_music_files_internal()

        # 再创建GUI
        self.create_gui()

    def _sync_to_shared(self):
        """同步当前状态到共享变量"""
        MusicPlayer._shared_audio_data = self.audio_data
        MusicPlayer._shared_sample_rate = self.sample_rate
        MusicPlayer._shared_channels = self.channels
        MusicPlayer._shared_total_length = self.total_length
        MusicPlayer._shared_current_position = self.current_position
        MusicPlayer._shared_current_index = self.current_index
        MusicPlayer._shared_is_playing = self.is_playing
        MusicPlayer._shared_is_paused = self.is_paused
        MusicPlayer._shared_music_files = self.music_files
        MusicPlayer._shared_song_name = self.current_song_name
        MusicPlayer._shared_thread = self.playback_thread
        MusicPlayer._shared_stop_event = self.stop_event
        MusicPlayer._shared_pause_event = self.pause_event
        MusicPlayer._shared_queue = self.audio_queue
        MusicPlayer._shared_stream = self.stream

    def _sync_from_shared(self):
        """从共享变量恢复状态"""
        self.audio_data = MusicPlayer._shared_audio_data
        self.sample_rate = MusicPlayer._shared_sample_rate
        self.channels = MusicPlayer._shared_channels
        self.total_length = MusicPlayer._shared_total_length
        self.current_position = MusicPlayer._shared_current_position
        self.current_index = MusicPlayer._shared_current_index
        self.is_playing = MusicPlayer._shared_is_playing
        self.is_paused = MusicPlayer._shared_is_paused
        self.music_files = (
            MusicPlayer._shared_music_files if MusicPlayer._shared_music_files else []
        )
        self.current_song_name = MusicPlayer._shared_song_name
        self.playback_thread = MusicPlayer._shared_thread
        self.stop_event = (
            MusicPlayer._shared_stop_event
            if MusicPlayer._shared_stop_event
            else threading.Event()
        )
        self.pause_event = (
            MusicPlayer._shared_pause_event
            if MusicPlayer._shared_pause_event
            else threading.Event()
        )
        self.audio_queue = (
            MusicPlayer._shared_queue
            if MusicPlayer._shared_queue
            else queue.Queue(maxsize=10)
        )
        self.stream = MusicPlayer._shared_stream

    def _is_gui_alive(self):
        """检查GUI是否仍然存在"""
        try:
            if self.parent is None:
                return False
            return self.parent.winfo_exists()
        except:
            return False

    def load_music_files_internal(self):
        """内部方法：仅加载文件列表到内存"""
        if self.music_files:  # 如果已经有文件列表，不需要重新加载
            return

        try:
            music_path = MUSIC_DIR
            
            # 如果目录不存在，创建并首次运行复制自带歌曲
            if not os.path.exists(music_path):
                os.makedirs(music_path, exist_ok=True)
                
                # 首次运行，复制自带歌曲
                bundled_music = resource_path("sound/music")
                if os.path.exists(bundled_music):
                    import shutil
                    for file in os.listdir(bundled_music):
                        if file.lower().endswith((".wav", ".mp3")):
                            src = os.path.join(bundled_music, file)
                            dst = os.path.join(music_path, file)
                            try:
                                shutil.copy2(src, dst)
                            except Exception as e:
                                print(f"复制自带歌曲失败: {e}")
            
            if os.path.exists(music_path):
                for file in os.listdir(music_path):
                    if file.lower().endswith((".wav", ".mp3")):
                        self.music_files.append(os.path.join(music_path, file))
        except Exception as e:
            print(f"读取失败: {e}")
        self.music_files.sort()

    def create_gui(self):
        """创建GUI"""
        # 检查 parent 是否是窗口（独立窗口）还是 Frame（嵌入标签页）
        is_window = hasattr(self.parent, "title") and callable(
            getattr(self.parent, "title")
        )

        if is_window:
            # 独立窗口模式
            self.parent.title("音乐播放器")
            self.parent.geometry("600x1000")
            self.parent.resizable(True, True)
            self.parent.configure(bg=self.pink_light)

            # 设置窗口图标
            try:
                icon_path = resource_path("gifs/ameath.ico")
                if os.path.exists(icon_path):
                    self.parent.iconbitmap(icon_path)
                # 使用 PNG 图标获得更好的清晰度
                png_path = resource_path("gifs/ameath_content.png")
                if os.path.exists(png_path):
                    from PIL import Image, ImageTk
                    img = Image.open(png_path)
                    photo = ImageTk.PhotoImage(img)
                    self.parent.iconphoto(True, photo)
            except Exception as e:
                print(f"设置窗口图标失败: {e}")

            screen_w = self.parent.winfo_screenwidth()
            screen_h = self.parent.winfo_screenheight()
            x = (screen_w - 600) // 2
            y = (screen_h - 1000) // 2
            self.parent.geometry(f"600x1000+{x}+{y}")

            # 独立窗口使用 blue_sky 背景
            main_frame = tk.Frame(self.parent, bg=self.blue_sky, padx=20, pady=15)
            main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        else:
            # 嵌入标签页模式，直接使用传入的 Frame
            main_frame = tk.Frame(self.parent, bg=self.pink_light, padx=20, pady=15)
            main_frame.pack(fill=tk.BOTH, expand=True)

        list_frame = tk.Frame(main_frame, bg=self.blue_sky)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.listbox = tk.Listbox(
            list_frame,
            selectmode=tk.SINGLE,
            font=("Microsoft YaHei UI", 10),
            bg=self.white,
            relief=tk.SOLID,
            borderwidth=1,
            yscrollcommand=scrollbar.set,
            selectbackground="#FFB6C1",
            selectforeground=self.text_dark,
        )
        self.listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.listbox.yview)

        self.current_song_label = tk.Label(
            main_frame,
            text=self.current_song_name,
            font=("Microsoft YaHei UI", 10, "italic"),
            bg=self.blue_sky,
            fg=self.text_light,
        )
        self.current_song_label.pack(pady=(5, 10))

        # 音量控制
        volume_frame = tk.Frame(main_frame, bg=self.blue_sky)
        volume_frame.pack(fill=tk.X, pady=(0, 15))

        tk.Label(
            volume_frame,
            text="音量:",
            font=("Microsoft YaHei UI", 10),
            bg=self.blue_sky,
            fg=self.text_dark,
        ).pack(side=tk.LEFT)

        self.volume_var = tk.IntVar(value=self.music_volume)
        self.volume_scale = tk.Scale(
            volume_frame,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            variable=self.volume_var,
            command=self.on_volume_change,
            bg=self.blue_sky,
            fg=self.text_dark,
            highlightthickness=0,
            length=200,
        )
        self.volume_scale.pack(side=tk.LEFT, padx=(5, 0))

        tk.Label(
            volume_frame,
            text="%",
            font=("Microsoft YaHei UI", 10),
            bg=self.blue_sky,
            fg=self.text_dark,
        ).pack(side=tk.LEFT, padx=(5, 0))

        progress_frame = tk.Frame(main_frame, bg=self.blue_sky)
        progress_frame.pack(fill=tk.X, pady=(0, 15))

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Scale(
            progress_frame,
            from_=0,
            to=100,
            variable=self.progress_var,
            orient=tk.HORIZONTAL,
            command=self.on_progress_change,
        )
        self.progress_bar.pack(fill=tk.X)

        self.time_label = tk.Label(
            progress_frame,
            text="0:00 / 0:00",
            font=("Microsoft YaHei UI", 9),
            bg=self.blue_sky,
            fg=self.text_light,
        )
        self.time_label.pack(pady=(5, 0))

        button_frame = tk.Frame(main_frame, bg=self.blue_sky)
        button_frame.pack(fill=tk.X, pady=(0, 10))

        prev_btn = tk.Button(
            button_frame,
            text="⏮ 上一首",
            command=self.previous_track,
            font=("Microsoft YaHei UI", 10),
            bg="#87CEFA",
            fg=self.text_dark,
            relief=tk.FLAT,
            padx=15,
            pady=8,
        )
        prev_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.play_pause_btn = tk.Button(
            button_frame,
            text=(
                "⏸ 暂停"
                if self.is_playing and not self.is_paused
                else ("▶ 继续" if self.is_paused else "▶ 播放")
            ),
            command=self.toggle_play_pause,
            font=("Microsoft YaHei UI", 10, "bold"),
            bg="#FFB6C1",
            fg=self.text_dark,
            relief=tk.FLAT,
            padx=20,
            pady=8,
        )
        self.play_pause_btn.pack(side=tk.LEFT, padx=(0, 10))

        next_btn = tk.Button(
            button_frame,
            text="下一首 ⏭",
            command=self.next_track,
            font=("Microsoft YaHei UI", 10),
            bg="#87CEFA",
            fg=self.text_dark,
            relief=tk.FLAT,
            padx=15,
            pady=8,
        )
        next_btn.pack(side=tk.LEFT)

        control_frame = tk.Frame(main_frame, bg=self.blue_sky)
        control_frame.pack(fill=tk.X, pady=(0, 15))

        import_btn = tk.Button(
            control_frame,
            text="📁 导入",
            command=self.import_music,
            font=("Microsoft YaHei UI", 9),
            bg="#98FB98",
            fg=self.text_dark,
            relief=tk.FLAT,
            padx=10,
            pady=5,
        )
        import_btn.pack(side=tk.LEFT, padx=(0, 10))

        refresh_btn = tk.Button(
            control_frame,
            text="🔄 刷新",
            command=self.refresh_music_list,
            font=("Microsoft YaHei UI", 9),
            bg="#DDA0DD",
            fg=self.text_dark,
            relief=tk.FLAT,
            padx=10,
            pady=5,
        )
        refresh_btn.pack(side=tk.LEFT)

        bottom_frame = tk.Frame(main_frame, bg=self.blue_sky)
        bottom_frame.pack(fill=tk.X, pady=(10, 0))

        cancel_btn = tk.Button(
            bottom_frame,
            text="取消",
            command=self.on_cancel,
            font=("Microsoft YaHei UI", 10),
            bg="#D3D3D3",
            fg=self.text_dark,
            relief=tk.FLAT,
            padx=15,
            pady=6,
        )
        cancel_btn.pack(side=tk.LEFT, padx=(0, 10))

        close_btn = tk.Button(
            bottom_frame,
            text="关闭(保持播放)",
            command=self.on_close_keep_playing,
            font=("Microsoft YaHei UI", 10),
            bg="#90EE90",
            fg=self.text_dark,
            relief=tk.FLAT,
            padx=15,
            pady=6,
        )
        close_btn.pack(side=tk.LEFT, padx=(0, 10))

        stop_btn = tk.Button(
            bottom_frame,
            text="停止并关闭",
            command=self.on_close,
            font=("Microsoft YaHei UI", 10),
            bg="#FFA07A",
            fg=self.text_dark,
            relief=tk.FLAT,
            padx=15,
            pady=6,
        )
        stop_btn.pack(side=tk.LEFT)

        self.listbox.bind("<Double-Button-1>", self.on_double_click)

        # 更新列表显示（现在listbox已经创建）
        self.update_listbox()

        # 如果有正在播放的歌曲，更新列表选中状态
        if 0 <= self.current_index < len(self.music_files):
            self.listbox.selection_set(self.current_index)
            self.listbox.see(self.current_index)

        self.update_progress()

    def on_volume_change(self, value):
        """音量变化回调"""
        volume = int(value)
        self.music_volume = volume
        # 保存配置
        config = load_config()
        config["music_volume"] = volume
        save_config(config)
        # 应用音量到当前播放（如果正在播放）
        self.apply_current_volume()

    def apply_current_volume(self):
        """应用当前音量到正在播放的音频"""
        # 注意：这个音乐播放器使用的是 sounddevice，不是 pygame
        # 音量控制在 feed_audio_thread 中处理
        pass

    def update_listbox(self):
        """更新列表框显示"""
        if self.listbox is None or not self._is_gui_alive():
            return

        try:
            self.listbox.delete(0, tk.END)
            for file in self.music_files:
                self.listbox.insert(tk.END, os.path.basename(file))

            if 0 <= self.current_index < len(self.music_files):
                self.listbox.selection_set(self.current_index)
                self.listbox.see(self.current_index)
        except tk.TclError:
            pass  # GUI已被销毁

    def import_music(self):
        """导入音乐文件"""
        files = filedialog.askopenfilenames(
            title="选择音乐文件",
            filetypes=[
                ("音频文件", "*.wav *.mp3"),
                ("WAV文件", "*.wav"),
                ("MP3文件", "*.mp3"),
                ("所有文件", "*.*"),
            ],
        )

        if not files:
            return

        music_path = MUSIC_DIR
        if not os.path.exists(music_path):
            os.makedirs(music_path, exist_ok=True)

        imported_count = 0
        for file in files:
            if file.lower().endswith((".wav", ".mp3")):
                filename = os.path.basename(file)
                dest_path = os.path.join(music_path, filename)

                counter = 1
                while os.path.exists(dest_path):
                    name, ext = os.path.splitext(filename)
                    dest_path = os.path.join(music_path, f"{name}_{counter}{ext}")
                    counter += 1

                try:
                    import shutil

                    shutil.copy2(file, dest_path)
                    imported_count += 1
                except Exception as e:
                    print(f"复制失败: {e}")

        if imported_count > 0:
            self.refresh_music_list()
            messagebox.showinfo("导入成功", f"成功导入 {imported_count} 个音乐文件！")

    def refresh_music_list(self):
        """刷新音乐列表"""
        self.load_music_files_internal()
        self.update_listbox()

    def on_double_click(self, event):
        """双击播放歌曲"""
        selection = self.listbox.curselection()
        if selection:
            index = selection[0]
            if index != self.current_index or not self.is_playing:
                self.current_index = index
                self.play_current_track()

    def load_wav_file(self, filepath):
        """加载音频文件（WAV/MP3）为 numpy array"""
        try:
            # 使用 soundfile 支持多种格式（WAV, MP3, OGG 等）
            import soundfile as sf

            data, samplerate = sf.read(filepath, dtype=np.float32)
            self.sample_rate = samplerate
            self.channels = 1 if len(data.shape) == 1 else data.shape[1]

            # 计算总时长（毫秒）
            self.total_length = int(len(data) * 1000 / self.sample_rate)

            return data

        except Exception as e:
            print(f"加载音频文件失败: {e}")
            return None

    def safe_stop_playback(self):
        self.stop_event.set()

        # 清空队列
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except:
                break

        # 关闭流
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except:
                pass
            self.stream = None

        # 只有在不是 playback_thread 本身时才 join
        if (
            self.playback_thread
            and self.playback_thread.is_alive()
            and self.playback_thread != threading.current_thread()
        ):
            self.playback_thread.join(timeout=0.5)

    def audio_callback(self, outdata, frames, time_info, status):
        """音频回调函数"""
        try:
            data = self.audio_queue.get_nowait()

            if len(data) < frames:
                padding = np.zeros(
                    (frames - len(data), self.channels), dtype=np.float32
                )
                data = np.concatenate([data, padding])
            elif len(data) > frames:
                data = data[:frames]

            # 应用音量（0-100%）
            volume_factor = self.music_volume / 100.0
            outdata[:] = (data * volume_factor).reshape(outdata.shape)

        except queue.Empty:
            outdata.fill(0)
            if self.stop_event.is_set():
                raise sd.CallbackStop()

    def feed_audio_thread(self, start_sample):
        """后台线程：将音频数据填入队列"""
        try:
            current = start_sample
            chunk_size = int(self.sample_rate * 0.05)

            while current < len(self.audio_data) and not self.stop_event.is_set():
                if self.pause_event.is_set():
                    self.paused_position = current
                    while self.pause_event.is_set() and not self.stop_event.is_set():
                        time.sleep(0.01)
                    if self.stop_event.is_set():
                        break
                    current = self.paused_position

                end = min(current + chunk_size, len(self.audio_data))
                chunk = self.audio_data[current:end]

                if len(chunk) < chunk_size:
                    if self.channels > 1:
                        padding = np.zeros(
                            (chunk_size - len(chunk), self.channels), dtype=np.float32
                        )
                    else:
                        padding = np.zeros(chunk_size - len(chunk), dtype=np.float32)
                    chunk = np.concatenate([chunk, padding])

                self.audio_queue.put(chunk, block=True)
                current = end
                self.current_position = current

            if not self.stop_event.is_set() and not self.pause_event.is_set():
                # 使用after方法安全地调用回调
                if self._is_gui_alive():
                    try:
                        self.parent.after(0, self.on_playback_finished)
                    except:
                        # GUI已关闭，直接调用下一首逻辑
                        self._auto_next_track()
                else:
                    # GUI已关闭，直接调用下一首逻辑
                    self._auto_next_track()

        except Exception as e:
            print(f"音频填充错误: {e}")

    def _auto_next_track(self):
        """自动播放下一首（无GUI版本）—— 由 playback_thread 调用"""

        # 更新索引
        if len(self.music_files) == 0:
            self.is_playing = False
            self._sync_to_shared()
            return

        if self.current_index >= len(self.music_files) - 1:
            self.current_index = 0
        else:
            self.current_index += 1

        # 等待一小会儿
        time.sleep(0.1)
        self.play_current_track_background()

    def _auto_next_track(self):
        """自动播放下一首（无GUI版本）"""
        # 先安全停止当前播放，确保资源释放
        self.safe_stop_playback()

        # 更新索引
        if len(self.music_files) > 0:
            if self.current_index >= len(self.music_files) - 1:
                self.current_index = 0
            else:
                self.current_index += 1

            # 延迟一下再播放下一首
            time.sleep(0.1)
            self.play_current_track_background()
        else:
            self.is_playing = False
            self._sync_to_shared()

    def on_playback_finished(self):
        """播放完成回调（GUI版本）"""
        self.is_playing = False

        # 安全地更新GUI
        if self._is_gui_alive() and self.play_pause_btn is not None:
            try:
                self.play_pause_btn.config(text="▶ 播放")
            except tk.TclError:
                pass

        self.next_track()

    def play_current_track(self):
        """播放当前选中的歌曲 - 先停止上一首"""
        # 先停止当前播放
        self.safe_stop_playback()

        if self.current_index < 0 or self.current_index >= len(self.music_files):
            return

        try:
            current_file = self.music_files[self.current_index]
            self.current_song_name = os.path.basename(current_file)

            # 安全地更新GUI
            if self._is_gui_alive() and self.current_song_label is not None:
                try:
                    self.current_song_label.config(
                        text=f"正在播放: {self.current_song_name}"
                    )
                except tk.TclError:
                    pass

            # 加载新音频
            self.audio_data = self.load_wav_file(current_file)

            if self.audio_data is None:
                if self._is_gui_alive():
                    messagebox.showerror("播放错误", "无法加载音频文件")
                return

            # 重置状态
            self.stop_event = threading.Event()
            self.pause_event = threading.Event()
            self.is_paused = False
            self.paused_position = 0
            self.current_position = 0
            self.audio_queue = queue.Queue(maxsize=10)

            # 创建输出流
            self.stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=np.float32,
                blocksize=int(self.sample_rate * 0.05),
                callback=self.audio_callback,
            )

            # 启动填充线程
            self.playback_thread = threading.Thread(
                target=self.feed_audio_thread, args=(0,)
            )
            self.playback_thread.daemon = True
            self.playback_thread.start()

            self.stream.start()

            self.is_playing = True

            # 安全地更新GUI
            if self._is_gui_alive() and self.play_pause_btn is not None:
                try:
                    self.play_pause_btn.config(text="⏸ 暂停")
                except tk.TclError:
                    pass

            # 同步到共享变量
            self._sync_to_shared()

        except Exception as e:
            print(f"播放失败: {str(e)}")
            self.is_playing = False
            self.is_paused = False
            if self._is_gui_alive() and self.play_pause_btn is not None:
                try:
                    self.play_pause_btn.config(text="▶ 播放")
                except tk.TclError:
                    pass

    def play_current_track_background(self):
        """后台播放（无GUI）"""
        if self.current_index < 0 or self.current_index >= len(self.music_files):
            return

        try:
            # === 关键：重置所有音频状态 ===
            self.audio_data = None
            self.sample_rate = None
            self.channels = None
            self.total_length = 0
            self.current_position = 0
            self.paused_position = 0
            # ==============================

            current_file = self.music_files[self.current_index]
            self.current_song_name = os.path.basename(current_file)

            self.audio_data = self.load_wav_file(current_file)
            if self.audio_data is None:
                return

            # 创建新事件对象（避免复用旧事件）
            self.stop_event = threading.Event()
            self.pause_event = threading.Event()
            self.is_paused = False
            self.audio_queue = queue.Queue(maxsize=10)

            # 创建新的 OutputStream
            self.stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=np.float32,
                blocksize=int(self.sample_rate * 0.05),
                callback=self.audio_callback,
            )

            # 启动新线程
            self.playback_thread = threading.Thread(
                target=self.feed_audio_thread, args=(0,), daemon=True
            )
            self.playback_thread.start()

            self.stream.start()
            self.is_playing = True
            self._sync_to_shared()

        except Exception as e:
            print(f"后台播放失败: {str(e)}")
            self.is_playing = False
            self.is_paused = False

    def toggle_play_pause(self):
        """切换播放/暂停"""
        if not self.is_playing and self.current_index >= 0:
            if self.is_paused:
                # 继续播放
                self.pause_event.clear()
                self.is_paused = False
                self.is_playing = True

                if self._is_gui_alive() and self.play_pause_btn is not None:
                    try:
                        self.play_pause_btn.config(text="⏸ 暂停")
                    except tk.TclError:
                        pass
            else:
                # 开始新播放
                self.play_current_track()
        elif self.is_playing:
            # 暂停
            self.pause_event.set()
            self.is_playing = False
            self.is_paused = True

            if self._is_gui_alive() and self.play_pause_btn is not None:
                try:
                    self.play_pause_btn.config(text="▶ 继续")
                except tk.TclError:
                    pass

        self._sync_to_shared()

    def previous_track(self):
        """播放上一首"""
        if len(self.music_files) == 0:
            return

        if self.current_index <= 0:
            self.current_index = len(self.music_files) - 1
        else:
            self.current_index -= 1

        if self._is_gui_alive() and self.listbox is not None:
            try:
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(self.current_index)
                self.listbox.see(self.current_index)
            except tk.TclError:
                pass

        self.play_current_track()

    def next_track(self):
        """播放下一首"""
        if len(self.music_files) == 0:
            return

        if self.current_index >= len(self.music_files) - 1:
            self.current_index = 0
        else:
            self.current_index += 1

        if self._is_gui_alive() and self.listbox is not None:
            try:
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(self.current_index)
                self.listbox.see(self.current_index)
            except tk.TclError:
                pass

        self.play_current_track()

    def on_progress_change(self, value):
        """处理进度条拖动"""
        if self.audio_data is not None:
            target_ms = (float(value) / 100.0) * self.total_length
            target_sample = int((target_ms / 1000.0) * self.sample_rate)

            was_playing = self.is_playing

            # 先停止当前播放
            self.safe_stop_playback()

            self.paused_position = target_sample
            self.current_position = target_sample

            if was_playing:
                # 重新启动播放
                self.stop_event = threading.Event()
                self.pause_event = threading.Event()
                self.is_paused = False
                self.audio_queue = queue.Queue(maxsize=10)

                self.stream = sd.OutputStream(
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    dtype=np.float32,
                    blocksize=int(self.sample_rate * 0.05),
                    callback=self.audio_callback,
                )

                self.playback_thread = threading.Thread(
                    target=self.feed_audio_thread, args=(target_sample,)
                )
                self.playback_thread.daemon = True
                self.playback_thread.start()

                self.stream.start()
                self.is_playing = True

                if self._is_gui_alive() and self.play_pause_btn is not None:
                    try:
                        self.play_pause_btn.config(text="⏸ 暂停")
                    except tk.TclError:
                        pass
            else:
                self.is_paused = True
                if self._is_gui_alive() and self.play_pause_btn is not None:
                    try:
                        self.play_pause_btn.config(text="▶ 继续")
                    except tk.TclError:
                        pass

            self._sync_to_shared()

    def update_progress(self):
        """更新进度条"""
        try:
            position_ms = (
                int(self.current_position * 1000 / self.sample_rate)
                if self.sample_rate
                else 0
            )

            if (self.is_playing or self.is_paused) and self._is_gui_alive():
                if self.total_length > 0:
                    progress = (position_ms / self.total_length) * 100

                    if self.progress_var is not None:
                        try:
                            self.progress_var.set(min(progress, 100))
                        except tk.TclError:
                            pass

                    if self.time_label is not None:
                        try:
                            current_sec = position_ms // 1000
                            total_sec = self.total_length // 1000
                            current_time = f"{current_sec // 60}:{current_sec % 60:02d}"
                            total_time = f"{total_sec // 60}:{total_sec % 60:02d}"
                            self.time_label.config(
                                text=f"{current_time} / {total_time}"
                            )
                        except tk.TclError:
                            pass

        except Exception as e:
            print(f"更新进度失败: {e}")

        # 即使GUI不存在也继续更新（为了保存位置）
        if self._is_gui_alive():
            try:
                self.parent.after(100, self.update_progress)
            except:
                pass

    def on_cancel(self):
        """取消操作 - 停止播放并关闭"""
        self.safe_stop_playback()
        self.parent.destroy()
        if self.position_unlock_callback:
            self.position_unlock_callback()

    def on_close_keep_playing(self):
        """关闭GUI但保持播放"""
        self._sync_to_shared()
        self.parent.destroy()
        if self.position_unlock_callback:
            self.position_unlock_callback()
        # 注意：播放继续在后台进行

    def on_close(self):
        """停止并关闭"""
        self.safe_stop_playback()
        # 清空共享状态
        MusicPlayer._shared_audio_data = None
        MusicPlayer._shared_is_playing = False
        MusicPlayer._shared_is_paused = False
        self.parent.destroy()
        if self.position_unlock_callback:
            self.position_unlock_callback()
