"""
Ameath 快捷菜单模块

本模块提供右键点击小爱时显示的快捷菜单，包括：
- 演出开始/结束（音乐播放控制）
- 跟随鼠标开关
- 暂停/继续
- 鼠标穿透
- 更多设置（打开完整设置窗口）

通过菜单项列表配置，可扩展
"""

import tkinter as tk
from typing import Callable, Dict, List, Optional, Any

from .config import load_config, save_config
from .fonts import get_font_config


class QuickMenuItem:
    """
    快捷菜单项基类
    
    用于定义菜单项的结构和行为，支持扩展自定义菜单项。
    """
    
    def __init__(
        self,
        label: Any = "",
        callback: Optional[Callable] = None,
        check_callback: Optional[Callable[[], bool]] = None,
        enabled_callback: Optional[Callable[[], bool]] = None,
        is_separator: bool = False,
    ):
        self.label = label
        self.callback = callback
        self.check_callback = check_callback
        self.enabled_callback = enabled_callback
        self.is_separator = is_separator
    
    def get_label(self) -> str:
        """获取显示文本"""
        if callable(self.label):
            return self.label()
        return self.label
    
    def is_checked(self) -> bool:
        """检查是否应该显示勾选状态"""
        if self.check_callback:
            return self.check_callback()
        return False
    
    def is_enabled(self) -> bool:
        """检查菜单项是否可用"""
        if self.enabled_callback:
            return self.enabled_callback()
        return True


class QuickContextMenu:
    """
    快捷菜单类
    
    在小爱旁边显示一个简洁的快捷操作菜单。
    """
    
    def __init__(self, pet, manager, version: str, tray_icon=None):
        """
        初始化快捷菜单
        
        Args:
            pet: DesktopGif 实例
            manager: PetManager 实例
            version: 版本号字符串
            tray_icon: 托盘图标实例（用于同步更新托盘菜单）
        """
        self.pet = pet
        self.manager = manager
        self.version = version
        self.tray_icon = tray_icon  # 托盘图标引用
        
        # 记录菜单打开前的暂停状态
        self._was_paused_before = False
        # 标记是否是菜单自动触发的临时暂停
        self._was_temporarily_paused = False
        
        # 窗口引用
        self.window: Optional[tk.Toplevel] = None
        
        # 加载样式配置
        self._load_styles()
        
        # 构建菜单项列表
        self._build_menu_items()
    
    def _load_styles(self):
        """加载样式配置（与完整设置页保持一致）"""
        self.colors = {
            "bg": "#FFF1F6",
            "card_bg": "#FFFFFF",
            "border": "#F3C2D4",
            "accent": "#FF69B4",
            "accent_dark": "#E84D8E",
            "text": "#4A2A3A",
            "subtext": "#7A5564",
            "hover": "#FFE1EE",
            "separator": "#F3C2D4",
        }
        
        font_config = get_font_config()
        # 使用较小的字体
        self.fonts = {
            "title": (font_config["family"], 11, "bold"),
            "base": (font_config["family"], 10),
            "small": (font_config["family"], 9),
        }
    
    def _build_menu_items(self):
        """构建菜单项列表"""
        self.menu_items: List[QuickMenuItem] = []
        
        # 音乐控制
        self.menu_items.append(QuickMenuItem(
            label=self._get_music_label,
            callback=self._toggle_music,
            enabled_callback=self._is_music_enabled,
        ))
        
        self.menu_items.append(QuickMenuItem(is_separator=True))
        
        # 行为控制
        self.menu_items.append(QuickMenuItem(
            label="跟随鼠标",
            callback=self._toggle_follow,
            check_callback=lambda: self.manager.follow_mouse,
        ))
        
        self.menu_items.append(QuickMenuItem(
            label=self._get_pause_label,
            callback=self._toggle_pause,
        ))
        
        self.menu_items.append(QuickMenuItem(
            label="鼠标穿透",
            callback=self._toggle_click_through,
            check_callback=lambda: self.manager.click_through,
        ))
        
        self.menu_items.append(QuickMenuItem(is_separator=True))
        
        # 显示控制
        self.menu_items.append(QuickMenuItem(
            label=self._get_visible_label,
            callback=self._toggle_visible,
        ))
        
        self.menu_items.append(QuickMenuItem(is_separator=True))
        
        # 其他
        self.menu_items.append(QuickMenuItem(
            label="更多设置...",
            callback=self._open_settings,
        ))
        
        self.menu_items.append(QuickMenuItem(
            label="退出",
            callback=self._quit,
        ))
    
    # ========================================================================
    # 菜单项回调方法
    # ========================================================================
    
    def _get_music_label(self) -> str:
        """获取音乐控制按钮的显示文本"""
        config = load_config()
        music_enabled = config.get("music_enabled", False)
        
        if not music_enabled:
            return "🎵 音乐（未启用）"
        
        from .music_player import MusicPlayer
        if MusicPlayer._shared_is_playing and not MusicPlayer._shared_is_paused:
            return "⏹ 停止演出"
        else:
            return "▶ 演出开始"
    
    def _is_music_enabled(self) -> bool:
        """检查音乐播放器是否启用"""
        config = load_config()
        return config.get("music_enabled", False)
    
    def _toggle_music(self):
        """切换音乐播放状态"""
        config = load_config()
        music_enabled = config.get("music_enabled", False)
        
        if not music_enabled:
            return
        
        from .music_player import MusicPlayer
        
        # 获取或创建 MusicPlayer 单例实例
        player = MusicPlayer._instance
        
        if player is None:
            # 创建隐藏的 Frame 作为 parent，初始化后台播放器
            hidden_frame = tk.Frame(self.pet.root)
            player = MusicPlayer(parent=hidden_frame, position_unlock_callback=None)
        
        # 确保有音乐文件列表
        if not player.music_files:
            player.load_music_files_internal()
        
        if not player.music_files:
            return
        
        # 调用实际的播放控制方法
        if player.is_playing and not player.is_paused:
            # 正在播放 -> 暂停
            player.pause_event.set()
            player.is_playing = False
            player.is_paused = True
            player._sync_to_shared()
        else:
            # 未播放或已暂停 -> 开始播放
            if player.current_index < 0 or player.current_index >= len(player.music_files):
                player.current_index = 0
            
            if player.is_paused and player.audio_data is not None:
                # 恢复播放
                player.pause_event.clear()
                player.is_playing = True
                player.is_paused = False
                player._sync_to_shared()
            else:
                # 开始新播放
                player.play_current_track()
        
        # 更新托盘菜单状态
        self._update_tray_menu()
    
    def _toggle_follow(self):
        """切换跟随鼠标"""
        self.manager.set_follow_mouse(not self.manager.follow_mouse)
        config = load_config()
        config["follow_mouse"] = self.manager.follow_mouse
        save_config(config)
        self._update_tray_menu()
    
    def _get_pause_label(self) -> str:
        """获取暂停按钮的显示文本"""
        # 如果是临时暂停状态，显示"暂停"（用户可以点击来真正暂停）
        # 如果是用户暂停状态，显示"继续"
        if self._was_temporarily_paused:
            return "⏸ 暂停"
        if self.pet.is_paused:
            return "▶ 继续"
        return "⏸ 暂停"
    
    def _toggle_pause(self):
        """切换暂停状态"""
        if self._was_temporarily_paused:
            # 当前是菜单临时暂停状态，用户点击"暂停"意味着要真正暂停
            # 取消临时暂停标记，让关闭菜单时不恢复运动
            self._was_temporarily_paused = False
            self._was_paused_before = True  # 标记为用户意图暂停
            # pet.is_paused 已经是 True，切换到正面idle帧
            self.pet.paused()  # 调用 paused() 切换到正面idle帧
            self.manager._sync_state_from_primary()
        elif self._was_paused_before:
            # 打开菜单前已经是暂停状态，用户点击"继续"
            # 调用 manager.toggle_pause 恢复运动
            self.manager.toggle_pause()
            self._was_paused_before = False
        else:
            # 正常情况（不应该到这里，但保留作为保险）
            self.manager.toggle_pause()
        self._update_tray_menu()
    
    def _toggle_click_through(self):
        """切换鼠标穿透"""
        self.manager.set_click_through(not self.manager.click_through)
        config = load_config()
        config["click_through"] = self.manager.click_through
        save_config(config)
        self._update_tray_menu()
    
    def _get_visible_label(self) -> str:
        """获取显示/隐藏按钮的显示文本"""
        if self.manager.is_visible():
            return "👁 隐藏"
        return "👁 显示"
    
    def _toggle_visible(self):
        """切换显示/隐藏"""
        if self.manager.is_visible():
            self.manager.hide_all()
        else:
            self.manager.show_all()
        self._update_tray_menu()
    
    def _open_settings(self):
        """打开完整设置窗口"""
        from .settings import show_settings_dialog
        show_settings_dialog(self.pet.root, self.manager, self.version)
    
    def _quit(self):
        """退出程序"""
        self.manager.request_quit()
    
    def _update_tray_menu(self):
        """更新托盘菜单（同步状态）"""
        if self.tray_icon is not None:
            try:
                # 重新创建菜单以反映新状态
                new_menu = self._create_tray_menu()
                self.tray_icon.menu = new_menu
                # 刷新托盘图标以显示更新后的菜单
                self.tray_icon.update_menu()
            except Exception:
                pass
    
    def _create_tray_menu(self):
        """创建托盘菜单（内部方法）"""
        import pystray
        
        def on_toggle_visible(icon, item):
            if self.manager.is_visible():
                self.manager.hide_all()
            else:
                self.manager.show_all()
            icon.menu = self._create_tray_menu()
        
        def on_toggle_pause(icon, item):
            self.manager.toggle_pause()
            icon.menu = self._create_tray_menu()
        
        def on_toggle_click_through(icon, item):
            self.manager.set_click_through(not self.manager.click_through)
            config = load_config()
            config["click_through"] = self.manager.click_through
            save_config(config)
            icon.menu = self._create_tray_menu()
        
        def on_toggle_follow(icon, item):
            self.manager.set_follow_mouse(not self.manager.follow_mouse)
            config = load_config()
            config["follow_mouse"] = self.manager.follow_mouse
            save_config(config)
            icon.menu = self._create_tray_menu()
        
        def on_settings(icon, item):
            from .settings import show_settings_dialog
            show_settings_dialog(self.pet.root, self.manager, self.version)
        
        def on_quit(icon):
            self.manager.request_quit()
        
        return pystray.Menu(
            pystray.MenuItem(
                lambda item: "隐藏" if self.manager.is_visible() else "显示",
                on_toggle_visible,
            ),
            pystray.MenuItem(
                lambda item: "暂停" if not self.manager.is_paused else "继续",
                on_toggle_pause,
            ),
            pystray.MenuItem(
                "跟随鼠标",
                on_toggle_follow,
                checked=lambda it: self.manager.follow_mouse,
            ),
            pystray.MenuItem(
                "鼠标穿透",
                on_toggle_click_through,
                checked=lambda it: self.manager.click_through,
            ),
            pystray.MenuItem("设置", on_settings),
            pystray.MenuItem("退出", on_quit),
        )
    
    # ========================================================================
    # 菜单显示方法
    # ========================================================================
    
    def show(self, x: int, y: int):
        """
        在指定位置显示快捷菜单
        
        Args:
            x: 屏幕 X 坐标
            y: 屏幕 Y 坐标
        """
        # 如果菜单已存在，先关闭它（恢复临时暂停状态）
        if self.window is not None and self.window.winfo_exists():
            self._on_close()  # 正确关闭并恢复状态
        
        # 记录菜单打开前的暂停状态
        self._was_paused_before = self.pet.is_paused
        self._was_temporarily_paused = False
        
        # 如果小爱未暂停，先临时暂停它（保持当前姿态）
        if not self._was_paused_before:
            self._was_temporarily_paused = True
            # 直接设置暂停状态，保持当前帧不变
            self.pet.is_paused = True
            self.pet.is_moving = False
            # 取消任何待执行的动画切换
            if self.pet.paused_anim is not None:
                self.pet.root.after_cancel(self.pet.paused_anim)
                self.pet.paused_anim = None
            if self.pet.screen_anim is not None:
                self.pet.root.after_cancel(self.pet.screen_anim)
                self.pet.screen_anim = None
        
        # 创建顶层窗口
        self.window = tk.Toplevel(self.pet.root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.configure(bg=self.colors["border"])
        
        # 绑定关闭时恢复状态
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # 创建内容容器
        content_frame = tk.Frame(
            self.window,
            bg=self.colors["card_bg"],
            bd=0,
            highlightthickness=1,
            highlightbackground=self.colors["border"],
        )
        content_frame.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        
        # 添加标题（缩小高度）
        title_frame = tk.Frame(content_frame, bg=self.colors["accent"], height=24)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)
        
        title_label = tk.Label(
            title_frame,
            text="✨ 快捷菜单",
            font=self.fonts["title"],
            bg=self.colors["accent"],
            fg="white",
            anchor="w",
            padx=8,
        )
        title_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 创建菜单项
        self._create_menu_items(content_frame)
        
        # 计算窗口位置
        self.window.update_idletasks()
        window_width = self.window.winfo_width()
        window_height = self.window.winfo_height()
        
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        
        # 确保窗口在屏幕内
        if x + window_width > screen_width:
            x = screen_width - window_width - 10
        if y + window_height > screen_height:
            y = screen_height - window_height - 10
        
        self.window.geometry(f"+{x}+{y}")
        
        # 绑定 Escape 键关闭
        self.window.bind("<Escape>", lambda e: self._on_close())
        
        # 点击窗口本身不关闭
        self.window.bind("<Button-1>", lambda e: None)
        
        # 绑定失去焦点时关闭
        self.window.bind("<FocusOut>", self._on_focus_out)
        
        # 聚焦窗口（不使用 grab_set，以便能检测点击外部）
        self.window.focus_force()
        
        # 延迟绑定全局点击检测（避免立即触发）
        self.window.after(100, self._bind_global_click)
    
    def _on_focus_out(self, event):
        """失去焦点时关闭菜单"""
        # 延迟检查，避免窗口刚打开时误触发
        self.window.after(50, self._check_focus)
    
    def _check_focus(self):
        """检查焦点状态"""
        if self.window is None or not self.window.winfo_exists():
            return
        # 如果焦点不在菜单窗口内，关闭菜单
        try:
            focus_widget = self.window.focus_get()
            if focus_widget is None or focus_widget.master != self.window:
                self._on_close()
        except Exception:
            pass
    
    def _on_close(self):
        """菜单关闭时的处理"""
        # 如果是菜单自动触发的临时暂停，恢复运动
        if self._was_temporarily_paused and self.pet.is_paused:
            self.pet.is_paused = False
            self.pet.is_moving = True
            # 恢复移动帧
            self.pet.current_frames = (
                self.pet.move_frames if self.pet.moving_right else self.pet.move_frames_left
            )
            self.pet.current_delays = self.pet.move_delays
            self.pet.frame_index = 0
            # 同步 manager 状态
            self.manager._sync_state_from_primary()
        
        self.hide()
    
    def _create_menu_items(self, parent: tk.Frame):
        """创建菜单项组件"""
        for item in self.menu_items:
            if item.is_separator:
                separator = tk.Frame(parent, bg=self.colors["separator"], height=1)
                separator.pack(fill=tk.X, padx=8, pady=3)
            else:
                self._create_menu_button(parent, item)
    
    def _create_menu_button(self, parent: tk.Frame, item: QuickMenuItem):
        """创建单个菜单按钮"""
        label = item.get_label()
        is_checked = item.is_checked()
        is_enabled = item.is_enabled()
        
        # 按钮文本
        if is_checked:
            text = f"✓ {label}"
        else:
            text = f"  {label}"
        
        # 创建按钮容器（缩小内边距）
        btn_frame = tk.Frame(parent, bg=self.colors["card_bg"])
        btn_frame.pack(fill=tk.X, padx=2, pady=0)
        
        btn = tk.Label(
            btn_frame,
            text=text,
            font=self.fonts["base"],
            bg=self.colors["card_bg"],
            fg=self.colors["text"] if is_enabled else self.colors["subtext"],
            anchor="w",
            padx=8,
            pady=4,  # 缩小垂直内边距
            cursor="hand2" if is_enabled else "arrow",
        )
        btn.pack(fill=tk.X)
        
        if is_enabled and item.callback:
            def on_enter(e, b=btn, f=btn_frame):
                b.config(bg=self.colors["hover"])
                f.config(bg=self.colors["hover"])
            
            def on_leave(e, b=btn, f=btn_frame):
                b.config(bg=self.colors["card_bg"])
                f.config(bg=self.colors["card_bg"])
            
            def on_click(e, i=item):
                i.callback()
                self._on_close()
            
            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)
            btn.bind("<Button-1>", on_click)
    
    def _bind_global_click(self):
        """绑定全局点击检测"""
        if self.window is None or not self.window.winfo_exists():
            return
        self.window.bind_all("<Button-1>", self._check_click_outside, add="+")
    
    def _check_click_outside(self, event):
        """检查点击是否在菜单外部"""
        if self.window is None or not self.window.winfo_exists():
            return
        
        x = self.window.winfo_x()
        y = self.window.winfo_y()
        w = self.window.winfo_width()
        h = self.window.winfo_height()
        
        # 点击在菜单外部，关闭菜单
        if not (x <= event.x_root <= x + w and y <= event.y_root <= y + h):
            self._on_close()
    
    def hide(self):
        """隐藏菜单"""
        if self.window is not None:
            try:
                self.window.unbind_all("<Button-1>")
                self.window.grab_release()
                self.window.destroy()
            except Exception:
                pass
            self.window = None
    
    def is_visible(self) -> bool:
        """检查菜单是否可见"""
        return self.window is not None and self.window.winfo_exists()


def show_quick_menu(pet, manager, version: str, x: int, y: int, tray_icon=None) -> QuickContextMenu:
    """
    显示快捷菜单的便捷函数
    
    Args:
        pet: DesktopGif 实例
        manager: PetManager 实例
        version: 版本号
        x: 屏幕 X 坐标
        y: 屏幕 Y 坐标
        tray_icon: 托盘图标实例（可选）
    
    Returns:
        QuickContextMenu: 菜单实例
    """
    menu = QuickContextMenu(pet, manager, version, tray_icon)
    menu.show(x, y)
    return menu