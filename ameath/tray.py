import pystray
import os
import sys
from pystray import MenuItem  # 显式导入，解决打包后MenuItem不可用问题
from PIL import Image

from .config import load_config, save_config, set_auto_startup
from .constants import CONFIG_FILE, SCALE_OPTIONS, TRANSPARENCY_OPTIONS
from .dialogs import show_about_dialog
from .utils import resource_path


def create_tray(app, version):
    """创建系统托盘图标和菜单，返回 pystray.Icon 实例"""

    # 创建托盘图标（使用ameath.gif）
    try:
        icon_gif = Image.open(resource_path("gifs/ameath.gif"))
        icon_gif.seek(0)  # 取第一帧
        icon_image = icon_gif.convert("RGBA")
        icon_image = icon_image.resize((64, 64), Image.Resampling.LANCZOS)
    except Exception as e:
        print(f"加载托盘图标失败，使用默认图标: {e}")
        icon_image = Image.new("RGB", (64, 64), color="pink")

    # ============ 回调函数 ============

    def on_toggle_startup(icon, item):
        """切换开机自启"""
        app.auto_startup = not app.auto_startup
        set_auto_startup(app.auto_startup)
        config = load_config()
        config["auto_startup"] = app.auto_startup
        save_config(config)
        icon.menu = _create_menu(app)

    def on_toggle_visible(icon, item):
        """切换隐藏/显示"""
        if app.root.state() == "withdrawn":
            app.root.deiconify()
        else:
            app.root.withdraw()
        icon.menu = _create_menu(app)

    def on_toggle_pause(icon, item):
        """切换暂停/继续"""
        app.toggle_pause()
        icon.menu = _create_menu(app)

    def on_set_scale(icon, item, index):
        """设置缩放"""
        app.set_scale(index)
        icon.menu = _create_menu(app)

    def on_quit(icon):
        """退出（只发信号，主线程统一收尾）"""
        app._request_quit = True

    def on_toggle_click_through(icon, item):
        """切换鼠标穿透"""
        app.click_through = not app.click_through
        app.set_click_through(app.click_through)
        config = load_config()
        config["click_through"] = app.click_through
        save_config(config)
        icon.menu = _create_menu(app)

    def on_toggle_follow(icon, item):
        """切换跟随鼠标"""
        app.follow_mouse = not app.follow_mouse
        config = load_config()
        config["follow_mouse"] = app.follow_mouse
        save_config(config)
        icon.menu = _create_menu(app)

    # 缩放回调工厂
    def _make_scale_handler(index):
        def handler(icon, item):
            on_set_scale(icon, item, index)

        return handler

    scale_handlers = [_make_scale_handler(i) for i in range(len(SCALE_OPTIONS))]

    # 透明度回调
    def on_set_transparency(icon, item, index):
        """设置透明度"""
        app.set_transparency(index)
        icon.menu = _create_menu(app)

    def _make_transparency_handler(index):
        def handler(icon, item):
            on_set_transparency(icon, item, index)

        return handler

    transparency_handlers = [
        _make_transparency_handler(i) for i in range(len(TRANSPARENCY_OPTIONS))
    ]

    def open_config():
        """打开配置文件"""
        if not os.path.exists(CONFIG_FILE):
            print("错误", f"配置文件不存在：\n{CONFIG_FILE}")
            return

        try:
            if sys.platform == "win32":
                os.startfile(CONFIG_FILE)
            elif sys.platform == "darwin":  # macOS
                subprocess.run(["open", CONFIG_FILE])
            else:  # Linux 及其他
                subprocess.run(["xdg-open", CONFIG_FILE])
        except Exception as e:
            print("错误", f"无法打开配置文件：\n{e}")

    def on_about(icon, item):
        """显示关于信息"""
        show_about_dialog(app.root, version)

    # ============ 菜单构建 ============

    def _create_menu(app_instance):
        """动态创建菜单"""
        # 缩放子菜单
        scale_items = []
        for i in range(len(SCALE_OPTIONS)):
            scale_items.append(
                pystray.MenuItem(
                    f"{SCALE_OPTIONS[i]}x",
                    scale_handlers[i],
                    checked=lambda it, idx=i: app_instance.scale_index == idx,
                    radio=True,
                )
            )
        scale_menu = pystray.Menu(*scale_items)

        # 透明度子菜单
        transparency_items = []
        for i in range(len(TRANSPARENCY_OPTIONS)):
            label = f"{int(TRANSPARENCY_OPTIONS[i] * 100)}%"
            transparency_items.append(
                pystray.MenuItem(
                    label,
                    transparency_handlers[i],
                    checked=lambda it, idx=i: app_instance.transparency_index == idx,
                    radio=True,
                )
            )
        transparency_menu = pystray.Menu(*transparency_items)

        return (
            pystray.MenuItem(
                "隐藏" if app_instance.root.state() == "normal" else "显示",
                on_toggle_visible,
            ),
            pystray.MenuItem(
                "暂停" if not app_instance.is_paused else "继续",
                on_toggle_pause,
            ),
            pystray.MenuItem(
                "跟随鼠标",
                on_toggle_follow,
                checked=lambda it: app_instance.follow_mouse,
            ),
            pystray.MenuItem(
                "鼠标穿透",
                on_toggle_click_through,
                checked=lambda it: app_instance.click_through,
            ),
            pystray.MenuItem(
                "开机自启",
                on_toggle_startup,
                checked=lambda it: app_instance.auto_startup,
            ),
            pystray.MenuItem("缩放", scale_menu),
            pystray.MenuItem("透明度", transparency_menu),
            pystray.MenuItem("打开配置文件", open_config),
            pystray.MenuItem("关于", on_about),
            pystray.MenuItem("退出", on_quit),
        )

    # 创建菜单
    menu = _create_menu(app)

    icon = pystray.Icon("desktop_pet", icon_image, "远航星", menu)
    return icon
