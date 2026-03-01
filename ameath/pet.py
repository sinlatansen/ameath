import ctypes
from ctypes import wintypes
import os
import win32gui
import win32con
import random
import tkinter as tk
from typing import Any
from screeninfo import get_monitors

from .config import load_config, save_config, check_and_fix_startup
from .constants import (
    DEFAULT_SCREEN_INDEX,
    DEFAULT_SCALE_INDEX,
    DEFAULT_TRANSPARENCY_INDEX,
    DEFAULT_WANDER_IDLE_STAY_MODE,
    DEFAULT_VOICE_ENABLED,
    DEFAULT_VOICE_VOLUME,
    EDGE_ESCAPE_CHANCE,
    FOLLOW_DISTANCE,
    FOLLOW_START_DIST,
    FOLLOW_STOP_DIST,
    GIF_DIR,
    GWL_EXSTYLE,
    HWND_BOTTOM,
    HWND_TOPMOST,
    INERTIA_FACTOR,
    INTENT_FACTOR,
    JITTER,
    JITTER_INTERVAL,
    MAX_INTERVAL,
    MIN_INTERVAL,
    MOTION_CURIOUS,
    MOTION_FOLLOW,
    MOTION_REST,
    MOTION_WANDER,
    MOVE_INTERVAL,
    OUTSIDE_TARGET_CHANCE,
    RESPAWN_MARGIN,
    REST_CHANCE,
    REST_DISTANCE,
    REST_DURATION_MAX,
    REST_DURATION_MIN,
    SCALE_OPTIONS,
    SPEED_CURIOUS,
    SPEED_FOLLOW,
    SPEED_WANDER,
    SPEED_X,
    SPEED_Y,
    STAY_PUT_CHANCE,
    STOP_CHANCE,
    STOP_DURATION_MAX,
    STOP_DURATION_MIN,
    SWP_NOACTIVATE,
    SWP_NOMOVE,
    SWP_NOSIZE,
    SWP_SHOWWINDOW,
    TARGET_CHANGE_MAX,
    TARGET_CHANGE_MIN,
    TRANSPARENT_COLOR,
    TRANSPARENCY_OPTIONS,
    WS_EX_LAYERED,
    WS_EX_TRANSPARENT,
)
from .utils import flip_frames, load_gif_frames, resource_path
from .voice import VoicePlayer


class DesktopGif:
    app: Any = None  # 用于系统托盘

    def __init__(self, root):
        self.root = root
        self._request_quit = False  # 退出标志（主线程统一收尾）
        self.display_priority = 1
        self._hidden_by_fullscreen = False
        self._user_hidden = False  # 用户手动隐藏标志

        # 立即设置无边框，避免闪烁
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.config(bg=TRANSPARENT_COLOR)
        root.attributes("-transparentcolor", TRANSPARENT_COLOR)

        # 初始化语音播放器
        try:
            self.voice_player = VoicePlayer()
            # 加载语音配置
            voice_config = load_config()
            voice_enabled = voice_config.get("voice_enabled", DEFAULT_VOICE_ENABLED)
            voice_volume = voice_config.get("voice_volume", DEFAULT_VOICE_VOLUME)
            if self.voice_player:
                self.voice_player.set_enabled(voice_enabled)
                self.voice_player.set_volume(voice_volume)
        except Exception:
            self.voice_player = None

        # 加载配置
        config = load_config()
        self.total_screen = config.get("total_screen", True)
        self.screen_index = config.get("screen_index", DEFAULT_SCREEN_INDEX)
        self.scale_index = config.get("scale_index", DEFAULT_SCALE_INDEX)
        self.window_snap = config.get("window_snap", True)
        self.auto_startup = config.get("auto_startup", False)
        self.scale = SCALE_OPTIONS[self.scale_index]
        self.display_priority = config.get("display_priority", 1)
        self.wander_idle_stay_mode = config.get(
            "wander_idle_stay_mode", DEFAULT_WANDER_IDLE_STAY_MODE
        )

        # 捕获窗口的类名，可以用开源工具winspy获取
        self.snap_class_name = ["Notepad","TXGuiFoundation"]# 记事本和QQ
        self.snap_class_name_lower = {name.lower() for name in self.snap_class_name}
        # 捕获窗口的窗口名
        self.snap_window_name = ["微信"]
        self.snap_window_name_lower = {name.lower() for name in self.snap_window_name}
        # 窗口名非精确匹配
        self.snap_window_egg = ["鸣潮"]
        self.snap_window_egg_lower = {name.lower() for name in self.snap_window_egg}

        # 获取屏幕
        monitors = get_monitors()
        if self.screen_index < 0 or self.screen_index + 1 > len(monitors):
            target_monitor = monitors[0]
            print("屏幕设置非法,使用主屏")
            config["screen_index"] = 0
            save_config(config)
        else:
            target_monitor = monitors[self.screen_index]

        # 按屏幕模式获取屏幕高度和宽度
        left = float("inf")
        top = float("inf")
        right = float("-inf")
        bottom = float("-inf")
        if self.total_screen:
            # 多屏模式
            for m in monitors:
                left = min(left, m.x)
                top = min(top, m.y)
                right = max(right, m.x + m.width)
                bottom = max(bottom, m.y + m.height)
        else:
            # 单屏模式
            left = target_monitor.x
            top = target_monitor.y
            right = target_monitor.x + target_monitor.width
            bottom = target_monitor.y + target_monitor.height

        # 可活动区域
        self.screen_x = left
        self.screen_y = top
        self.screen_w = right
        self.screen_h = bottom
        # 检查开机自启路径是否正确（exe移动后自动修复）
        check_and_fix_startup()

        # ---------- 加载所有GIF ----------
        # 加载move.gif (使用 resource_path 支持打包)
        move_path = resource_path(os.path.join(GIF_DIR, "move.gif"))
        self.move_frames, self.move_delays, self.move_pil_frames = load_gif_frames(
            move_path, self.scale
        )
        # 加载翻转的move帧（向左）
        self.move_frames_left = flip_frames(self.move_pil_frames)

        # 加载idle1~4.gif
        self.idle_gifs = []
        for i in range(1, 5):
            idle_path = resource_path(os.path.join(GIF_DIR, f"idle{i}.gif"))
            frames, delays, _ = load_gif_frames(idle_path, self.scale)
            self.idle_gifs.append((frames, delays))

        # 加载screen1~4.gif
        self.screen_gifs = []
        for i in range(1, 5):
            screen_path = resource_path(os.path.join(GIF_DIR, f"screen{i}.gif"))
            frames, delays, _ = load_gif_frames(screen_path, self.scale)
            self.screen_gifs.append((frames, delays))

        # 加载drag.gif（拖动时显示）
        drag_path = resource_path(os.path.join(GIF_DIR, "drag.gif"))
        self.drag_frames, self.drag_delays, _ = load_gif_frames(drag_path, self.scale)

        # 加载paused的GIF
        paused_path = resource_path(os.path.join(GIF_DIR, "idle2.gif"))
        self.paused_frames, self.paused_delays, _ = load_gif_frames(
            paused_path, self.scale
        )

        # 加载screen的GIF
        screen_path = resource_path(os.path.join(GIF_DIR, "screen1.gif"))
        self.screen_frames, self.screen_delays, _ = load_gif_frames(
            screen_path, self.scale
        )

        # 当前状态
        self.current_frames = self.move_frames
        self.current_delays = self.move_delays
        self.is_moving = True
        self.is_paused = False  # 暂停状态
        self.is_screen = False  # 窗口捕获状态
        self.is_idle_playing = False
        self.idle_allows_move = False
        self.moving_right = True  # 当前移动方向
        self.frame_index = 0
        self.dragging = False  # 拖动状态
        self.drag_start_x = 0
        self.drag_start_y = 0
        self._pre_drag_frames = None  # 保存拖动前的帧
        self._pre_drag_delays = None
        self._drag_animating = False  # 拖动时是否在播放动画
        
        # 程序运行使用
        self.old_screen = False # 窗口捕获状态对比用
        self.screen_anim = None # 窗口贴靠动画ID
        self.paused_anim = None # 暂停动画ID
        self._window_check_counter = 0  # 窗口检测帧计数
        self._cached_window_rect = None  # 缓存的窗口矩形
        
        self.label = tk.Label(root, bg=TRANSPARENT_COLOR, bd=0)
        self.label.pack()

        self.w = self.current_frames[0].width()
        self.h = self.current_frames[0].height()

        # 初始出现在屏幕随机位置（配合多开）
        self.x = random.randint(self.screen_x, self.screen_w - self.w)
        self.y = random.randint(self.screen_y, self.screen_h - self.h)
        root.geometry(f"{self.w}x{self.h}+{self.x}+{self.y}")

        # 强制刷新，让 winfo_x/y 生效
        root.update_idletasks()

        # 加载鼠标穿透配置并设置
        config = load_config()
        self.click_through = config.get("click_through", True)
        self.follow_mouse = config.get("follow_mouse", False)
        self.set_click_through(self.click_through)

        # 加载透明度配置并设置
        self.transparency_index = config.get(
            "transparency_index", DEFAULT_TRANSPARENCY_INDEX
        )
        self.set_transparency(self.transparency_index)

        self.vx = SPEED_X
        self.vy = SPEED_Y

        # 运动系统：目标点和计时器（立即设置一个随机目标，不要当前位置）
        self.target_x, self.target_y = self.get_random_target()
        self.target_timer = random.randint(TARGET_CHANGE_MIN, TARGET_CHANGE_MAX)

        # 状态机变量
        self.motion_state = MOTION_WANDER  # 当前运动状态
        self.rest_timer = 0  # 休息计时器

        # 绑定拖动事件
        self.label.bind("<ButtonPress-1>", self.start_drag)
        self.label.bind("<B1-Motion>", self.do_drag)
        self.label.bind("<ButtonRelease-1>", self.stop_drag)

        self.animate()
        self.move()

        # 获取正确的窗口句柄
        self.root.update_idletasks()
        self.hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())

        # 应用显示优先级
        self.set_display_priority(self.display_priority, persist=False)

        # 启动轻量级可见性轮询（替代Shell Hook）
        self.root.after(500, self.ensure_visibility)

        # 启动退出轮询（主线程统一收尾）
        self.root.after(100, self.check_quit)

        # 绑定右键事件
        self.label.bind("<Button-3>", self.handle_right_click)

    def handle_right_click(self, event):
        """处理右键点击事件 - 打开设置窗口音乐标签页"""
        config = load_config()
        music_enabled = config.get("music_enabled", False)

        if music_enabled:
            # 打开设置窗口并切换到音乐标签页
            from .settings import show_settings_dialog
            from .utils import get_version

            # 使用 manager（PetManager）而不是 app（Icon）
            manager = getattr(self, "manager", None)
            if manager:
                show_settings_dialog(
                    self.root, manager, get_version(), open_music_tab=True
                )

    def ensure_visibility(self):
        """轻量级可见性轮询（替代Shell Hook）"""
        try:
            # 如果用户手动隐藏，不自动恢复显示
            if self._user_hidden:
                pass
            elif self.display_priority == 1:
                self._apply_topmost()
            elif self.display_priority == 2:
                self._apply_fullscreen_hide()
            else:
                self._apply_desktop_only()
        except Exception:
            pass
        self.root.after(500, self.ensure_visibility)

    def _apply_topmost(self):
        if self._hidden_by_fullscreen:
            self.root.deiconify()
            self._hidden_by_fullscreen = False
        self.root.attributes("-topmost", True)
        ctypes.windll.user32.SetWindowPos(
            self.hwnd,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )

    def _apply_fullscreen_hide(self):
        if self._is_fullscreen_window_active():
            if not self._hidden_by_fullscreen:
                self.root.withdraw()
                self._hidden_by_fullscreen = True
            return
        if self._hidden_by_fullscreen:
            self.root.deiconify()
            self._hidden_by_fullscreen = False
        self._apply_topmost()

    def _apply_desktop_only(self):
        if self._hidden_by_fullscreen:
            self.root.deiconify()
            self._hidden_by_fullscreen = False
        if self._is_desktop_foreground():
            self._apply_topmost()
            return
        self.root.attributes("-topmost", False)
        ctypes.windll.user32.SetWindowPos(
            self.hwnd,
            HWND_BOTTOM,
            0,
            0,
            0,
            0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )

    def _is_desktop_foreground(self):
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return False
            class_name = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetClassNameW(hwnd, class_name, 256)
            return class_name.value in {"Progman", "WorkerW"}
        except Exception:
            return False

    def _is_fullscreen_window_active(self):
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd or hwnd == self.hwnd:
                return False
            class_name = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetClassNameW(hwnd, class_name, 256)
            if class_name.value in {"Progman", "WorkerW"}:
                return False
            rect = wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            screen_w = self.screen_w
            screen_h = self.screen_h
            return width >= screen_w and height >= screen_h
        except Exception:
            return False

    def check_quit(self):
        """主线程轮询退出标志（确保托盘在主线程正确销毁）"""
        if self._request_quit:
            try:
                if hasattr(self, "app") and self.app:
                    self.app.stop()  # 在主线程 stop 托盘
            except Exception:
                pass
            self.root.destroy()
            return
        self.root.after(100, self.check_quit)

    def set_click_through(self, enable):
        """设置鼠标穿透"""
        try:
            # 动态获取窗口句柄
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if enable:
                ctypes.windll.user32.SetWindowLongW(
                    hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT
                )
            else:
                ctypes.windll.user32.SetWindowLongW(
                    hwnd, GWL_EXSTYLE, style & ~WS_EX_TRANSPARENT
                )
        except Exception as e:
            print(f"设置鼠标穿透失败: {e}")

    def set_transparency(self, index):
        """设置透明度"""
        self.transparency_index = index
        alpha = TRANSPARENCY_OPTIONS[index]
        self.root.attributes("-alpha", alpha)
        # 保存配置
        config = load_config()
        config["transparency_index"] = index
        save_config(config)

    def set_display_priority(self, mode, persist=True):
        """设置显示优先级"""
        self.display_priority = mode
        if persist:
            config = load_config()
            config["display_priority"] = mode
            save_config(config)
        try:
            # 如果用户手动隐藏，不改变窗口可见性
            if self._user_hidden:
                return
            if self.display_priority == 1:
                self._apply_topmost()
            elif self.display_priority == 2:
                self._apply_fullscreen_hide()
            else:
                self._apply_desktop_only()
        except Exception:
            pass

    def set_wander_idle_stay_mode(self, mode):
        """设置游荡停驻模式"""
        self.wander_idle_stay_mode = mode
        config = load_config()
        config["wander_idle_stay_mode"] = mode
        save_config(config)

    def stop_drag(self, event):
        """停止拖动"""
        self.dragging = False
        # 恢复拖动前的帧
        if self._pre_drag_frames is not None:
            self.current_frames = self._pre_drag_frames
            self.current_delays = self._pre_drag_delays
            self.frame_index = 0

    def set_scale(self, index):
        """设置缩放"""
        self.scale_index = index
        self.scale = SCALE_OPTIONS[index]
        config = load_config()
        config["scale_index"] = index
        save_config(config)

        # 重新加载GIF (使用 resource_path 支持打包)
        move_path = resource_path(os.path.join(GIF_DIR, "move.gif"))
        result = load_gif_frames(move_path, self.scale)
        if result[0]:  # 确保有帧
            self.move_frames, self.move_delays, self.move_pil_frames = result
            self.move_frames_left = flip_frames(self.move_pil_frames)
        else:
            print("加载move.gif失败")
            return

        self.idle_gifs = []
        for i in range(1, 5):
            idle_path = resource_path(os.path.join(GIF_DIR, f"idle{i}.gif"))
            result = load_gif_frames(idle_path, self.scale)
            if result[0]:
                self.idle_gifs.append((result[0], result[1]))
        # 确保有idle帧可用
        if not self.idle_gifs:
            self.idle_gifs.append((self.move_frames, self.move_delays))

        self.screen_gifs = []
        for i in range(1, 5):
            screen_path = resource_path(os.path.join(GIF_DIR, f"screen{i}.gif"))
            result = load_gif_frames(screen_path, self.scale)
            if result[0]:
                self.screen_gifs.append((result[0], result[1]))
        # 确保有帧可用
        if not self.screen_gifs:
            self.screen_gifs.append((self.move_frames, self.move_delays))

        # 重新加载drag.gif
        drag_path = resource_path(os.path.join(GIF_DIR, "drag.gif"))
        drag_result = load_gif_frames(drag_path, self.scale)
        if drag_result[0]:
            self.drag_frames, self.drag_delays, _ = drag_result

        # 重新加载paused的GIF
        paused_path = resource_path(os.path.join(GIF_DIR, "idle2.gif"))
        paused_result = load_gif_frames(paused_path, self.scale)
        if paused_result[0]:
            self.paused_frames, self.paused_delays, _ = paused_result

        # 重新加载screen的GIF
        screen_path = resource_path(os.path.join(GIF_DIR, "screen1.gif"))
        self.screen_frames, self.screen_delays, _ = load_gif_frames(
            screen_path, self.scale
        )

        # 更新窗口大小
        if self.move_frames:
            self.w = self.move_frames[0].width()
            self.h = self.move_frames[0].height()
            self.root.geometry(f"{self.w}x{self.h}+{int(self.x)}+{int(self.y)}")

        # 重置帧索引，切换到move帧
        self.frame_index = 0
        self.current_frames = (
            self.move_frames if self.moving_right else self.move_frames_left
        )
        self.current_delays = self.move_delays

    def toggle_pause(self):
        """切换暂停/继续"""
        self.is_paused = not self.is_paused
        if self.is_paused:
            # 暂停：停止移动，切换到暂停模式
            self.paused()
        else:
            # 继续：恢复移动
            self.is_moving = True
            self.current_frames = (
                self.move_frames if self.moving_right else self.move_frames_left
            )
            self.current_delays = self.move_delays
            self.frame_index = 0

    def start_drag(self, event):
        """开始拖动（鼠标穿透关闭时才可用）"""
        if self.click_through:
            return
        self.dragging = True
        # 记录鼠标相对于窗口左上角的偏移量
        self.drag_start_x = event.x
        self.drag_start_y = event.y
        # 保存当前帧状态
        self._pre_drag_frames = self.current_frames
        self._pre_drag_delays = self.current_delays
        # 切换到drag动态显示
        self.current_frames = self.drag_frames
        self.current_delays = self.drag_delays
        self.frame_index = 0
        self.label.config(image=self.current_frames[0])

        # 播放随机语音（如果启用）
        if self.voice_player:
            self.voice_player.play_random_voice()

    def do_drag(self, event):
        """拖动中"""
        if self.dragging:
            # 窗口左上角 = 鼠标当前位置 - 偏移量
            self.x = event.x_root - self.drag_start_x
            self.y = event.y_root - self.drag_start_y
            self.root.geometry(f"+{int(self.x)}+{int(self.y)}")

    def paused(self):
        self.frame_index = 0
        interval = random.randint(MIN_INTERVAL, MAX_INTERVAL)
        if self.window_snap:
            if self.is_screen:
                self.current_frames = self.screen_frames
                self.current_delays = self.screen_delays
                self.screen_anim = self.root.after(interval, self.paused_to_screen)
                # 取消paused动画
                if self.paused_anim is not None:
                    self.root.after_cancel(self.paused_anim)
                    self.paused_anim = None
            else:
                self.current_frames = self.paused_frames
                self.current_delays = self.paused_delays
                self.paused_anim = self.root.after(interval, self.paused_to_idle)
                # 取消screen动画
                if self.screen_anim is not None:
                    self.root.after_cancel(self.screen_anim)
                    self.screen_anim = None
        else:
            self.current_frames = self.paused_frames
            self.current_delays = self.paused_delays
            self.paused_anim = self.root.after(interval, self.paused_to_idle)
            # 取消screen动画
            if self.screen_anim is not None:
                self.root.after_cancel(self.screen_anim)
                self.screen_anim = None

    def paused_to_idle(self):
        """切换到随机idle状态（暂停状态）"""
        # 播放 idle 动画
        frames, delays = random.choice(self.idle_gifs)
        self.current_frames = frames
        self.current_delays = delays
        self.frame_index = 0
        # 随机停止一段时间后恢复暂停模式
        stop_duration = random.randint(STOP_DURATION_MIN, STOP_DURATION_MAX)
        self.root.after(stop_duration, self.paused)

    def paused_to_screen(self):
        """切换到随机screen状态（暂停状态）"""
        # 播放 screen 动画
        frames, delays = random.choice(self.screen_gifs)
        self.current_frames = frames
        self.current_delays = delays
        self.frame_index = 0
        # 随机停止一段时间后恢复暂停模式
        stop_duration = random.randint(STOP_DURATION_MIN, STOP_DURATION_MAX)
        self.root.after(stop_duration, self.paused)

    def switch_to_idle(self):
        """切换到随机idle状态（随机停下功能）"""
        # 如果是暂停状态跳转paused
        if self.is_paused:
            stop_duration = random.randint(STOP_DURATION_MIN, STOP_DURATION_MAX)
            self.root.after(stop_duration, self.paused)

        self.is_idle_playing = False
        self.idle_allows_move = False

        if self.wander_idle_stay_mode == 0:
            # 始终移动：播放 idle 动画，但继续移动
            self.is_idle_playing = True
            self.idle_allows_move = True
            self.is_moving = True
        elif self.wander_idle_stay_mode == 2:
            # 停驻：始终播放 idle 动画并停留
            self.is_idle_playing = True
            self.idle_allows_move = False
            self.is_moving = False
        else:
            # 概率停驻：0.3 概率播放动画；若播放，0.5 概率停驻/移动
            if random.random() < STAY_PUT_CHANCE:
                self.is_idle_playing = True
                self.idle_allows_move = random.random() >= 0.5
                self.is_moving = self.idle_allows_move
            else:
                # 不播放动画，停在原地
                self.is_idle_playing = False
                self.idle_allows_move = False
                self.is_moving = False

        if self.is_idle_playing:
            frames, delays = random.choice(self.idle_gifs)
            self.current_frames = frames
            self.current_delays = delays
            self.frame_index = 0
        else:
            # 不播放 idle 动画时，显示随机 idle 静帧
            frames, delays = random.choice(self.idle_gifs)
            self.current_frames = frames
            self.current_delays = delays
            self.frame_index = random.randint(0, max(0, len(frames) - 1))

        stop_duration = random.randint(STOP_DURATION_MIN, STOP_DURATION_MAX)
        self.root.after(stop_duration, self.switch_to_move)

    def switch_to_move(self):
        """切换到移动状态"""
        # 如果是暂停状态，不处理
        if self.is_paused:
            return
        self.is_idle_playing = False
        self.idle_allows_move = False
        self.is_moving = True
        self.current_frames = (
            self.move_frames if self.moving_right else self.move_frames_left
        )
        self.current_delays = self.move_delays
        self.frame_index = 0

    # 获取目前激活窗口数据
    def get_window_rect_by_title(self):
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None
        # 判断窗口是否有效且可见
        if win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
            class_name = win32gui.GetClassName(hwnd)
            window_name = win32gui.GetWindowText(hwnd)
            window_name_lower = window_name.strip().lower()
            # 判断窗口是否需要捕获
            if class_name.lower() in self.snap_class_name_lower or window_name_lower in self.snap_window_name_lower or any(name in window_name_lower for name in self.snap_window_egg_lower):
                try:
                    # 判断是否窗口化
                    placement = win32gui.GetWindowPlacement(hwnd)
                    show_cmd = placement[1]
                    if show_cmd is not win32con.SW_SHOWMINIMIZED and show_cmd is not win32con.SW_SHOWMAXIMIZED:
                        return win32gui.GetWindowRect(hwnd)
                except Exception:
                    return None
        return None

    # ============ 运动系统方法 ============

    def get_random_target(self):
        """获取随机目标点（偶尔在屏幕外，触发边缘效果）"""
        # 使用配置的概率，让宠物尝试冲边界
        if random.random() < OUTSIDE_TARGET_CHANCE:
            side = random.choice(["left", "right", "top", "bottom"])
            margin = RESPAWN_MARGIN + 50  # 比重生距离再远一点
            if side == "left":
                return (-margin, random.randint(self.screen_y, self.screen_h - self.h))
            elif side == "right":
                return (
                    self.screen_w + margin,
                    random.randint(self.screen_y, self.screen_h - self.h),
                )
            elif side == "top":
                return (random.randint(self.screen_x, self.screen_w - self.w), -margin)
            else:  # bottom
                return (
                    random.randint(self.screen_x, self.screen_w - self.w),
                    self.screen_h + margin,
                )
        else:
            return (
                random.randint(self.screen_x, self.screen_w - self.w),
                random.randint(self.screen_y, self.screen_h - self.h),
            )

    def get_follow_target(self):
        """获取跟随鼠标的目标点"""
        mx = self.root.winfo_pointerx()
        my = self.root.winfo_pointery()
        # 保持一定距离，不要贴脸
        offset = FOLLOW_DISTANCE
        tx = mx + random.randint(-offset, offset)
        ty = my + random.randint(-offset, offset)
        # 限制在屏幕内
        tx = max(self.screen_x, min(self.screen_w - self.w, tx))
        ty = max(self.screen_y, min(self.screen_h - self.h, ty))
        return tx, ty

    def respawn_from_edge(self):
        """从屏幕边缘外侧重生"""
        side = random.choice(["left", "right", "top", "bottom"])
        if side == "left":
            self.x = -RESPAWN_MARGIN
            self.y = random.randint(self.screen_y, self.screen_h - self.h)
        elif side == "right":
            self.x = self.screen_w + RESPAWN_MARGIN
            self.y = random.randint(self.screen_y, self.screen_h - self.h)
        elif side == "top":
            self.y = -RESPAWN_MARGIN
            self.x = random.randint(self.screen_x, self.screen_w - self.w)
        else:  # bottom
            self.y = self.screen_h + RESPAWN_MARGIN
            self.x = random.randint(self.screen_x, self.screen_w - self.w)

        # 给一点入场速度
        self.vx = random.choice([-3, 3])
        self.vy = random.randint(-2, 2)

    def handle_edge(self):
        """处理边缘：反弹或出屏重生"""
        escaped = False

        # 检测是否出屏
        if self.x < self.screen_x or self.x > self.screen_w - self.w:
            escaped = True
        if self.y < self.screen_y or self.y > self.screen_h - self.h:
            escaped = True

        if escaped:
            if random.random() < EDGE_ESCAPE_CHANCE:
                self.respawn_from_edge()
                return True
            else:
                # 反弹
                self.vx = -self.vx
                self.vy = -self.vy
                # 拉回屏幕内
                self.x = max(self.screen_x, min(self.screen_w - self.w, self.x))
                self.y = max(self.screen_y, min(self.screen_h - self.h, self.y))
        return False

    # ============ 动画方法 ============

    def animate(self):
        if not self.current_frames:
            self.root.after(100, self.animate)
            return
        self.label.config(image=self.current_frames[self.frame_index])
        delay = self.current_delays[self.frame_index] if self.current_delays else 100

        self.frame_index = (self.frame_index + 1) % len(self.current_frames)
        self.root.after(delay, self.animate)

    def move(self):
        """运动状态机主循环（性能优化版）"""
        # 拖动时停止自动运动
        if self.dragging:
            self.root.after(50, self.move)
            return

        # 暂停时停止所有运动并切换对应功能
        if self.is_paused:
            self.root.after(100, self.move)
            if self.window_snap:
                # 判断是否特定程序
                # 带间隔检测优化，每10帧约500ms检测一次
                self._window_check_counter += 1
                if self._window_check_counter >= 10:
                    self._window_check_counter = 0
                    self._cached_window_rect = self.get_window_rect_by_title()
                rect = self._cached_window_rect
                if rect:
                    # 记录窗口贴靠前位置
                    if not self.is_screen:
                        self.paused_x = self.x
                        self.paused_y = self.y
                    left, top, right, bottom = rect
                    pet_x = right - self.w # 贴靠右上角
                    pet_y = top - self.h + 5 # 趴在顶部
                    # 检查生成窗口范围
                    if pet_x > self.screen_x and pet_x < self.screen_w - self.w and pet_y > self.screen_y and pet_y < self.screen_h - self.h:
                        self.root.geometry(f"{self.w}x{self.h}+{pet_x}+{pet_y}")
                        self.is_screen = True
                    else:
                        self.is_screen = False
                else:
                    self.is_screen = False
                if self.old_screen != self.is_screen:
                    # 回到窗口贴靠前位置
                    if not self.is_screen:
                        self.root.geometry(f"+{int(self.paused_x)}+{int(self.paused_y)}")
                    self.old_screen = self.is_screen
                    self.paused()
            return
            
        # ============ 随机停下休息（游荡模式专属） ============
        if self.motion_state == MOTION_WANDER and self.is_moving:
            if not self.is_idle_playing and random.random() < STOP_CHANCE:
                self.switch_to_idle()
                self.root.after(MOVE_INTERVAL, self.move)
                return

        # ============ 休息状态 ============
        if self.motion_state == MOTION_REST:
            self.rest_timer -= MOVE_INTERVAL
            if self.rest_timer <= 0:
                # 休息结束，恢复游荡
                self.motion_state = MOTION_WANDER
                self.target_x, self.target_y = self.get_random_target()
                self.target_timer = random.randint(TARGET_CHANGE_MIN, TARGET_CHANGE_MAX)
                self.switch_to_move()
            self.root.after(MOVE_INTERVAL, self.move)
            return

        # idle 播放中保持原地不动
        if not self.is_moving:
            self.root.after(MOVE_INTERVAL, self.move)
            return

        # ============ 鼠标位置缓存 ============
        mx = self.root.winfo_pointerx()
        my = self.root.winfo_pointery()
        mouse_moved = (mx, my) != getattr(self, "_last_mouse", (mx, my))
        self._last_mouse = (mx, my)

        # ============ 计算到目标的距离 ============
        dx = self.target_x - self.x
        dy = self.target_y - self.y
        dist = (dx * dx + dy * dy) ** 0.5

        # ============ 状态判断与切换 ============

        # 如果关闭了跟随模式，强制重置为游荡模式
        if not self.follow_mouse and self.motion_state in (
            MOTION_FOLLOW,
            MOTION_CURIOUS,
        ):
            self.motion_state = MOTION_WANDER

        # 跟随模式：根据距离切换follow/curious
        if self.follow_mouse:
            dist_mouse = ((mx - self.x) ** 2 + (my - self.y) ** 2) ** 0.5

            if dist_mouse > FOLLOW_START_DIST:
                self.motion_state = MOTION_FOLLOW
            elif dist_mouse < FOLLOW_STOP_DIST:
                self.motion_state = MOTION_CURIOUS

        # 游荡模式：到达目标后决定是否休息
        elif self.motion_state == MOTION_WANDER and dist < REST_DISTANCE:
            if random.random() < REST_CHANCE:
                # 休息一下
                if self.wander_idle_stay_mode == 0:
                    self.target_x, self.target_y = self.get_random_target()
                    self.target_timer = random.randint(
                        TARGET_CHANGE_MIN, TARGET_CHANGE_MAX
                    )
                else:
                    if not self.is_idle_playing:
                        self.motion_state = MOTION_REST
                        self.rest_timer = random.randint(
                            REST_DURATION_MIN, REST_DURATION_MAX
                        )
                        self.switch_to_idle()
                        self.root.after(MOVE_INTERVAL, self.move)
                        return
            else:
                # 继续游荡，换个目标
                self.target_x, self.target_y = self.get_random_target()
                self.target_timer = random.randint(TARGET_CHANGE_MIN, TARGET_CHANGE_MAX)

        # ============ 定时更换目标（仅游荡模式） ============
        if self.motion_state == MOTION_WANDER:
            self.target_timer -= 1
            if self.target_timer <= 0:
                self.target_x, self.target_y = self.get_random_target()
                self.target_timer = random.randint(TARGET_CHANGE_MIN, TARGET_CHANGE_MAX)

        # ============ 计算速度倍率 ============
        if self.motion_state == MOTION_WANDER:
            speed_mul = SPEED_WANDER
        elif self.motion_state == MOTION_FOLLOW:
            speed_mul = SPEED_FOLLOW
        elif self.motion_state == MOTION_CURIOUS:
            speed_mul = SPEED_CURIOUS
        else:
            speed_mul = 1.0

        # ============ 跟随/好奇模式：只在鼠标移动时更新目标 ============
        if self.motion_state in (MOTION_FOLLOW, MOTION_CURIOUS):
            if mouse_moved:  # 只有鼠标移动时才更新目标
                if self.motion_state == MOTION_FOLLOW:
                    offset = FOLLOW_DISTANCE
                else:  # curious
                    offset = FOLLOW_STOP_DIST
                self.target_x = mx + random.randint(-offset, offset)
                self.target_y = my + random.randint(-offset, offset)

                # 重新计算距离
                dx = self.target_x - self.x
                dy = self.target_y - self.y
                dist = max(1, (dx * dx + dy * dy) ** 0.5)

        # ============ 朝目标移动（惯性 + 意图） ============
        desired_vx = dx / dist * SPEED_X * speed_mul
        desired_vy = dy / dist * SPEED_Y * speed_mul

        # 惯性融合
        self.vx = self.vx * INERTIA_FACTOR + desired_vx * INTENT_FACTOR
        self.vy = self.vy * INERTIA_FACTOR + desired_vy * INTENT_FACTOR

        # ============ 抖动降频：每N帧更新一次 ============
        if not hasattr(self, "_move_tick"):
            self._move_tick = 0
        self._move_tick += 1

        if self._move_tick % JITTER_INTERVAL == 0:
            self._jitter_x = random.uniform(-JITTER, JITTER)
            self._jitter_y = random.uniform(-JITTER, JITTER)
        self.vx += getattr(self, "_jitter_x", 0)
        self.vy += getattr(self, "_jitter_y", 0)

        # 应用移动
        self.x += self.vx
        self.y += self.vy

        # ============ 边缘处理 ============
        if not self.handle_edge():
            # 没出屏时才检查边界碰撞
            hit_edge = False
            if self.x <= self.screen_x:
                self.x = self.screen_x
                self.vx = abs(self.vx)  # 向右反弹
                hit_edge = True
            elif self.x + self.w >= self.screen_w:
                self.x = self.screen_w - self.w
                self.vx = -abs(self.vx)  # 向左反弹
                hit_edge = True

            if self.y <= self.screen_y:
                self.y = self.screen_y
                self.vy = abs(self.vy)  # 向下
                hit_edge = True
            elif self.y + self.h >= self.screen_h:
                self.y = self.screen_h - self.h
                self.vy = -abs(self.vy)  # 向上
                hit_edge = True

            # 撞边时更新方向状态
            new_moving_right = self.vx > 0.5
            new_moving_left = self.vx < -0.5

            if self.is_idle_playing:
                hit_edge = False
            if new_moving_right and not self.moving_right and not self.is_idle_playing:
                self.moving_right = True
                self.current_frames = self.move_frames
                self.current_delays = self.move_delays
                self.frame_index = 0
            elif new_moving_left and self.moving_right and not self.is_idle_playing:
                self.moving_right = False
                self.current_frames = self.move_frames_left
                self.current_delays = self.move_delays
                self.frame_index = 0

        # 只在位置明显变化时更新geometry
        ix, iy = int(self.x), int(self.y)
        last_pos = getattr(self, "_last_pos", None)
        if (ix, iy) != last_pos:
            self.root.geometry(f"+{ix}+{iy}")
            self._last_pos = (ix, iy)

        self.root.after(MOVE_INTERVAL, self.move)
