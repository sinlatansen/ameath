"""关于标签页"""

import tkinter as tk
from tkinter import ttk
import webbrowser

from PIL import Image, ImageTk

from ..constants import GITEE_RELEASES_URL
from ..utils import resource_path


def create_about_tab(settings_window, parent):
    """创建关于标签页

    Args:
        settings_window: SettingsWindow 实例
        parent: 父容器

    Returns:
        创建的标签页 frame
    """
    frame = ttk.Frame(parent, padding=20)

    # 顶部留白
    tk.Frame(frame, height=15, bg=settings_window.colors["bg"]).pack()

    # 显示 ameath.gif
    try:
        gif_image = Image.open(resource_path("gifs/ameath.gif"))
        gif_image = gif_image.resize((100, 100), Image.Resampling.LANCZOS)
        gif_photo = ImageTk.PhotoImage(gif_image)
        gif_label = tk.Label(
            frame, image=gif_photo, border=0, bg=settings_window.colors["bg"]
        )
        gif_label.image = gif_photo  # type: ignore[attr-defined]
        gif_label.pack(pady=(0, 15))
    except Exception as e:
        print(f"加载关于窗口GIF失败: {e}")

    # 标题
    tk.Label(
        frame,
        text="飞吧，朝向春天",
        font=(settings_window.font_family, 20, "bold"),
        fg=settings_window.colors["accent_dark"],
        bg=settings_window.colors["bg"],
    ).pack(pady=(0, 10))

    # 版本号
    tk.Label(
        frame,
        text=f"版本 {settings_window.version}",
        font=settings_window.fonts["base"],
        fg=settings_window.colors["subtext"],
        bg=settings_window.colors["bg"],
    ).pack(pady=(0, 5))

    # Git Hash
    if settings_window.git_hash:
        tk.Label(
            frame,
            text=f"Build: {settings_window.git_hash}",
            font=settings_window.fonts["small"],
            fg=settings_window.colors["subtext"],
            bg=settings_window.colors["bg"],
        ).pack(pady=(0, 15))
    else:
        tk.Frame(frame, height=10, bg=settings_window.colors["bg"]).pack()

    # 分隔线
    separator = ttk.Separator(frame, orient="horizontal")
    separator.pack(fill=tk.X, pady=10)

    # 描述文本
    desc_frame = tk.Frame(frame, bg=settings_window.colors["bg"])
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
            font=settings_window.fonts["base"],
            fg=settings_window.colors["text"],
            bg=settings_window.colors["bg"],
            justify=tk.CENTER,
        ).pack(pady=2)

    # 分隔线
    separator2 = ttk.Separator(frame, orient="horizontal")
    separator2.pack(fill=tk.X, pady=10)

    # 链接区域
    links_frame = tk.Frame(frame, bg=settings_window.colors["bg"])
    links_frame.pack(pady=10)

    # Gitee Release 链接
    link1 = tk.Frame(links_frame, bg=settings_window.colors["bg"])
    link1.pack(pady=5)
    tk.Label(
        link1,
        text="软件发布页: ",
        font=settings_window.fonts["base"],
        fg=settings_window.colors["text"],
        bg=settings_window.colors["bg"],
    ).pack(side=tk.LEFT)
    link1_text = tk.Label(
        link1,
        text="Gitee Release",
        font=settings_window.fonts["base"],
        fg=settings_window.colors["accent"],
        bg=settings_window.colors["bg"],
        cursor="hand2",
    )
    link1_text.pack(side=tk.LEFT)
    link1_text.bind("<Button-1>", lambda e: webbrowser.open(GITEE_RELEASES_URL))

    # B站链接
    link2 = tk.Frame(links_frame, bg=settings_window.colors["bg"])
    link2.pack(pady=5)
    tk.Label(
        link2,
        text="作者: ",
        font=settings_window.fonts["base"],
        fg=settings_window.colors["text"],
        bg=settings_window.colors["bg"],
    ).pack(side=tk.LEFT)
    link2_text = tk.Label(
        link2,
        text="b站-fugu-",
        font=settings_window.fonts["base"],
        fg=settings_window.colors["accent"],
        bg=settings_window.colors["bg"],
        cursor="hand2",
    )
    link2_text.pack(side=tk.LEFT)
    link2_text.bind(
        "<Button-1>",
        lambda e: webbrowser.open("https://space.bilibili.com/84508966"),
    )

    return frame
