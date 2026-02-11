import itertools
import os
import subprocess
import sys

from PIL import Image, ImageTk

from .constants import GITEE_RELEASES_URL


# ============ PyInstaller 资源路径处理 ============
def resource_path(relative_path):
    """获取打包后的资源绝对路径"""
    try:
        # PyInstaller 创建的临时目录
        base_path = sys._MEIPASS  # type: ignore
    except AttributeError:
        # 开发环境
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def get_version():
    """自动获取当前git标签版本"""
    # 1. 优先读取 version.txt（打包后独立运行）
    try:
        version_path = resource_path("version.txt")
        if os.path.exists(version_path):
            with open(version_path, "r", encoding="utf-8") as f:
                version = f.read().strip()
            if version:
                return version
    except Exception:
        pass

    # 2. 回退：尝试从 git 获取
    try:
        version = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if version:
            return version
    except Exception:
        pass

    return "dev"


def check_new_version():
    """检查Gitee是否有新版本"""
    import re
    import urllib.request

    try:
        req = urllib.request.Request(
            GITEE_RELEASES_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode("utf-8")

        # 提取最新版本的标签名 (格式: <a href="/lzy-buaa-jdi/ameath/releases/tag/v1.1.1">v1.1.1</a>)
        pattern = r'href="/lzy-buaa-jdi/ameath/releases/tag/(v[^"]+)"'
        matches = re.findall(pattern, html)
        if matches:
            return matches[0]
    except Exception as e:
        print(f"检查版本失败: {e}")
    return None


def check_update(current_version):
    """检查更新，返回 (latest_version, release_notes) 或 None"""
    import re
    import urllib.request

    try:
        req = urllib.request.Request(
            GITEE_RELEASES_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode("utf-8")

        # 提取最新版本的标签名
        pattern = r'href="/lzy-buaa-jdi/ameath/releases/tag/(v[^"]+)"'
        matches = re.findall(pattern, html)
        if matches:
            latest_version = matches[0]
            # 尝试提取发布说明
            release_notes = ""
            # 简单提取HTML中的文本作为发布说明
            notes_pattern = r'<div class="release-notes[^"]*">(.*?)</div>'
            notes_matches = re.findall(notes_pattern, html, re.DOTALL)
            if notes_matches:
                # 移除HTML标签
                notes_text = re.sub(r"<[^>]+>", "", notes_matches[0])
                release_notes = notes_text.strip()
            return (latest_version, release_notes)
    except Exception as e:
        print(f"检查更新失败: {e}")
    return None


def normalize_version(v):
    """标准化版本号用于比较"""
    v = v.lstrip("v")
    parts = v.split(".")
    if v == "dev" or not v:
        return []
    try:
        return [int(p) for p in parts if p.isdigit()]
    except Exception:
        return []


def version_greater_than(v1, v2):
    """比较两个版本号，v1 > v2 返回 True"""
    parts1 = normalize_version(v1)
    parts2 = normalize_version(v2)
    if not parts1 or not parts2:
        return False
    max_len = max(len(parts1), len(parts2))
    parts1 = parts1 + [0] * (max_len - len(parts1))
    parts2 = parts2 + [0] * (max_len - len(parts2))
    return parts1 > parts2


def flip_frames(pil_frames):
    """水平翻转所有PIL Image帧，返回PhotoImage"""
    flipped = []
    for img in pil_frames:
        flipped_img = ImageTk.PhotoImage(img.transpose(Image.Transpose.FLIP_LEFT_RIGHT))
        flipped.append(flipped_img)
    return flipped


def load_gif_frames(gif_path, scale=1.0):
    """加载并缩放GIF，返回(photoimage_frames, delays, pil_frames)"""
    photoimage_frames = []
    pil_frames = []
    delays = []
    gif = Image.open(gif_path)
    frame = None
    for i in itertools.count():
        try:
            gif.seek(i)
            frame = gif.convert("RGBA")
            w, h = frame.size
            new_w, new_h = int(w * scale), int(h * scale)
            # 确保缩放后尺寸有效
            if new_w <= 0 or new_h <= 0:
                new_w = max(1, new_w)
                new_h = max(1, new_h)
            resized = frame.resize((new_w, new_h), Image.Resampling.LANCZOS)
            photoimage_frames.append(ImageTk.PhotoImage(resized))
            pil_frames.append(resized)
            delays.append(gif.info.get("duration", 80))
        except EOFError:
            break
    # 确保至少有一帧
    if not photoimage_frames and frame is not None:
        photoimage_frames.append(
            ImageTk.PhotoImage(frame.resize((100, 100), Image.Resampling.LANCZOS))
        )
        pil_frames.append(frame.resize((100, 100), Image.Resampling.LANCZOS))
        delays.append(80)
    return photoimage_frames, delays, pil_frames
