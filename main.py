import ctypes
import sys
import threading
import tkinter as tk

# 启用 Windows DPI 感知（解决高DPI屏幕模糊问题）
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def main():
    from ameath.config import load_config
    from ameath.dialogs import show_update_dialog
    from ameath.pet import DesktopGif
    from ameath.utils import check_new_version, get_version, version_greater_than

    VERSION = get_version()

    def check_version_and_notify(root):
        """检查版本并通知（后台线程调用）"""
        latest = check_new_version()
        if latest and version_greater_than(latest, VERSION):
            config = load_config()
            if config.get("skip_updates"):
                return
            if config.get("skip_version") == latest:
                return
            # 在主线程显示弹窗
            root.after(0, lambda: show_update_dialog(root, latest, VERSION))

    root = tk.Tk()
    # 立即隐藏窗口，避免闪烁
    root.withdraw()

    # 后台检查版本（非阻塞）
    threading.Thread(target=check_version_and_notify, args=(root,), daemon=True).start()

    # 尝试导入pystray
    try:
        from ameath.tray import create_tray

        app = DesktopGif(root)

        icon = create_tray(app, VERSION)
        app.app = icon

        # 延迟启动托盘，让窗口完全初始化后再显示
        root.update_idletasks()
        root.deiconify()  # 显示窗口（避免边框闪烁）
        root.after(500, lambda: icon.run_detached())

        root.mainloop()

    except ImportError:
        # 没有pystray时正常运行窗口
        print("未安装pystray，将只显示窗口。可运行: pip install pystray")
        root.deiconify()  # 显示窗口
        DesktopGif(root)
        root.mainloop()


if __name__ == "__main__":
    main()
