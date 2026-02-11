import itertools
import json
import os
import subprocess
import sys
import time

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


def _fetch_latest_release():
    """获取最新 release 信息（Gitee API）"""
    import urllib.request

    api_url = "https://gitee.com/api/v5/repos/lzy-buaa-jdi/ameath/releases/latest"
    req = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        },
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        data = response.read().decode("utf-8")
    return json.loads(data)


def _select_release_asset(assets):
    """选择可下载资源，优先 exe，其次包含 ameath 的 zip"""
    if not assets:
        return None, None

    def _pick(predicate):
        for asset in assets:
            name = (asset.get("name") or "").lower()
            if predicate(name):
                return asset.get("browser_download_url"), asset.get("name")
        return None, None

    url, name = _pick(lambda n: n.endswith(".exe"))
    if url:
        return url, name

    url, name = _pick(lambda n: n.endswith(".zip") and "ameath" in n)
    if url:
        return url, name

    url, name = _pick(lambda n: n.endswith(".zip"))
    return url, name


def check_update(current_version):
    """检查更新，返回 (latest_version, release_notes, asset_url, asset_name) 或 None"""
    try:
        release = _fetch_latest_release()
        latest_version = release.get("tag_name") or release.get("name")
        if not latest_version:
            return None
        release_notes = release.get("body") or ""
        asset_url, asset_name = _select_release_asset(release.get("assets", []))
        return (latest_version, release_notes, asset_url, asset_name)
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


def _download_file(url, target_path):
    import urllib.request

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        with open(target_path, "wb") as f:
            f.write(response.read())


def _write_update_script(
    script_path,
    current_exe,
    update_mode,
    source_path,
    cleanup_files,
    cleanup_dirs,
    pid,
):
    lines = [
        "@echo off",
        "setlocal",
        f"set PID={pid}",
        f"set CUR_EXE={current_exe}",
        f"set SRC={source_path}",
        'for %%I in ("%CUR_EXE%") do set EXE_NAME=%%~nxI',
        ":wait",
        'tasklist /FI "PID eq %PID%" | find "%PID%" >nul',
        "if not errorlevel 1 (timeout /t 1 >nul & goto wait)",
    ]
    if update_mode == "dir":
        lines.extend(
            [
                'for %%I in ("%CUR_EXE%") do set APP_DIR=%%~dpI',
                'xcopy /y /e /i "%SRC%\\*" "%APP_DIR%" >nul',
            ]
        )
    else:
        lines.extend(
            [
                "set RETRY=0",
                ":copy_retry",
                'attrib -r "%CUR_EXE%" >nul 2>&1',
                'copy /y "%SRC%" "%CUR_EXE%" >nul',
                "if errorlevel 1 (",
                "  set /a RETRY+=1",
                "  if %RETRY% GEQ 10 goto copy_fail",
                "  timeout /t 1 >nul",
                "  goto copy_retry",
                ")",
                "goto copy_ok",
                ":copy_fail",
                "echo update copy failed",
                "goto end",
                ":copy_ok",
            ]
        )
    lines.extend(
        [
            "echo update finished",
        ]
    )
    for path in cleanup_files:
        lines.append(f'del /f /q "{path}"')
    for path in cleanup_dirs:
        lines.append(f'rmdir /s /q "{path}"')
    lines.append(":end")
    lines.append('del "%~f0"')
    with open(script_path, "w", encoding="utf-8") as f:
        f.write("\r\n".join(lines))


def download_and_update(asset_url, asset_name):
    """下载更新并通过 bat 完成自我替换，返回 None 或错误信息"""
    if not asset_url or not asset_name:
        return "未找到可下载的更新文件"

    if not getattr(sys, "frozen", False):
        return "开发环境无法自动更新"

    app_dir = os.path.dirname(sys.executable)
    current_exe = sys.executable
    temp_name = f"_update_{int(time.time())}_{asset_name}"
    download_path = os.path.join(app_dir, temp_name)
    cleanup_files = []
    cleanup_dirs = []

    try:
        _download_file(asset_url, download_path)
        cleanup_files.append(download_path)

        update_mode = "exe"
        source_path = None
        if asset_name.lower().endswith(".zip"):
            import zipfile

            extract_dir = os.path.join(app_dir, f"_update_extract_{int(time.time())}")
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(download_path, "r") as zf:
                zf.extractall(extract_dir)
            cleanup_dirs.append(extract_dir)

            exe_candidates = []
            extracted_files = []
            for root, _, files in os.walk(extract_dir):
                for filename in files:
                    extracted_files.append(os.path.join(root, filename))
                    if filename.lower().endswith(".exe"):
                        exe_candidates.append(os.path.join(root, filename))

            if not exe_candidates:
                return "压缩包内未找到可执行文件"

            exe_candidates.sort(
                key=lambda p: ("ameath" not in os.path.basename(p).lower(), p)
            )
            if len(extracted_files) == 1 and len(exe_candidates) == 1:
                source_path = exe_candidates[0]
                update_mode = "exe"
            else:
                source_path = extract_dir
                update_mode = "dir"
        elif asset_name.lower().endswith(".exe"):
            source_path = download_path
        else:
            return "不支持的更新文件类型"

        script_path = os.path.join(app_dir, "_ameath_update.bat")
        _write_update_script(
            script_path,
            current_exe,
            update_mode,
            source_path,
            cleanup_files,
            cleanup_dirs,
            os.getpid(),
        )

        try:
            os.startfile(script_path)
        except Exception:
            subprocess.Popen(
                ["cmd", "/c", "start", "", script_path],
                cwd=app_dir,
                shell=False,
            )
        return None
    except Exception as e:
        return str(e)


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
