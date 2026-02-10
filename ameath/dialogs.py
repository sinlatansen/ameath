import tkinter as tk
import webbrowser

from PIL import Image, ImageTk

from .config import load_config, save_config
from .constants import GITEE_RELEASES_URL
from .utils import resource_path


def show_update_dialog(parent, latest_version, current_version):
    """显示版本更新通知弹窗"""
    dialog = tk.Toplevel(parent)
    dialog.title("发现新版本")
    width, height = 520, 300
    dialog.geometry(f"{width}x{height}")
    dialog.resizable(False, False)
    dialog.attributes("-topmost", True)
    dialog.transient(parent)
    try:
        dialog.iconbitmap(resource_path("gifs/ameath.ico"))
    except Exception as e:
        print(f"设置更新窗口图标失败: {e}")

    # 居中显示
    dialog.update_idletasks()
    screen_w = dialog.winfo_screenwidth()
    screen_h = dialog.winfo_screenheight()
    x = (screen_w - width) // 2
    y = (screen_h - height) // 2
    dialog.geometry(f"+{x}+{y}")

    # 内容
    tk.Label(
        dialog,
        text="发现新版本！",
        font=("Microsoft YaHei UI", 16, "bold"),
    ).pack(pady=(25, 15))

    tk.Label(
        dialog,
        text=f"当前版本: {current_version}",
        font=("Microsoft YaHei UI", 12),
    ).pack()

    tk.Label(
        dialog,
        text=f"最新版本: {latest_version}",
        font=("Microsoft YaHei UI", 12),
    ).pack(pady=(5, 20))

    # 按钮
    btn_frame = tk.Frame(dialog)
    btn_frame.pack(pady=(0, 25))

    def on_download():
        webbrowser.open(GITEE_RELEASES_URL)
        dialog.destroy()

    def on_skip():
        config = load_config()
        config["skip_updates"] = True
        save_config(config)
        dialog.destroy()

    tk.Button(
        btn_frame,
        text="前往发布",
        command=on_download,
        width=12,
        font=("Microsoft YaHei UI", 11),
        bg="#1890FF",
        fg="white",
    ).pack(side=tk.LEFT, padx=15)

    tk.Button(
        btn_frame,
        text="不再提醒",
        command=on_skip,
        width=12,
        font=("Microsoft YaHei UI", 11),
        bg="#999999",
        fg="white",
    ).pack(side=tk.LEFT, padx=15)

    dialog.focus_force()


def show_about_dialog(parent, current_version):
    """显示关于信息"""
    about_window = tk.Toplevel(parent)
    about_window.title("飞吧，朝向春天")
    about_window.geometry("700x550")
    about_window.resizable(False, False)
    about_window.attributes("-topmost", True)

    # 设置窗口图标
    try:
        icon_image = Image.open(resource_path("gifs/ameath.gif"))
        icon_image = icon_image.resize((64, 64), Image.Resampling.LANCZOS)
        icon_pil = icon_image.convert("RGBA")
        app_icon = ImageTk.PhotoImage(icon_pil)
        about_window.iconphoto(True, app_icon)
    except Exception:
        pass

    # 居中显示
    about_window.update_idletasks()
    screen_w = about_window.winfo_screenwidth()
    screen_h = about_window.winfo_screenheight()
    x = (screen_w - 700) // 2
    y = (screen_h - 550) // 2
    about_window.geometry(f"+{x}+{y}")

    # 主内容 Frame
    content_frame = tk.Frame(about_window)
    content_frame.pack(fill=tk.BOTH, expand=True, padx=30, pady=20)

    # 显示 ameath.gif
    try:
        gif_image = Image.open(resource_path("gifs/ameath.gif"))
        gif_image = gif_image.resize((100, 100), Image.Resampling.LANCZOS)
        gif_photo = ImageTk.PhotoImage(gif_image)
        gif_label = tk.Label(content_frame, image=gif_photo, border=0)
        gif_label.image = gif_photo  # type: ignore[attr-defined]
        gif_label.pack(pady=(0, 15))
    except Exception as e:
        print(f"加载关于窗口GIF失败: {e}")

    # 标题
    tk.Label(
        content_frame,
        text="飞吧，朝向春天",
        font=("Microsoft YaHei UI", 20, "bold"),
    ).pack(pady=(0, 20))

    # 版本号
    tk.Label(
        content_frame,
        text=f"版本: {current_version}",
        font=("Microsoft YaHei UI", 12),
    ).pack(pady=(0, 15))

    # Gitee Release 链接
    def open_gitee():
        webbrowser.open("https://gitee.com/lzy-buaa-jdi/ameath/releases")

    link1 = tk.Frame(content_frame)
    link1.pack(pady=(0, 8))
    tk.Label(
        link1,
        text="软件发布页: ",
        font=("Microsoft YaHei UI", 12),
    ).pack(side=tk.LEFT)
    link1_text = tk.Label(
        link1,
        text="Gitee Release",
        font=("Microsoft YaHei UI", 12),
        fg="#1890FF",
        cursor="hand2",
    )
    link1_text.pack(side=tk.LEFT)
    link1_text.bind("<Button-1>", lambda e: open_gitee())

    # B站链接
    def open_bili():
        webbrowser.open("https://space.bilibili.com/84508966")

    link2 = tk.Frame(content_frame)
    link2.pack(pady=(0, 25))
    tk.Label(
        link2,
        text="作者: ",
        font=("Microsoft YaHei UI", 12),
    ).pack(side=tk.LEFT)
    link2_text = tk.Label(
        link2,
        text="b站-fugu-",
        font=("Microsoft YaHei UI", 12),
        fg="#1890FF",
        cursor="hand2",
    )
    link2_text.pack(side=tk.LEFT)
    link2_text.bind("<Button-1>", lambda e: open_bili())

    # 关闭按钮
    tk.Button(
        content_frame,
        text="确定",
        command=about_window.destroy,
        width=12,
        font=("Microsoft YaHei UI", 11),
    ).pack(pady=(10, 0))
