# Windows 桌面宠物窗口层级管理模块
# 通过挂载到正确的 WorkerW 实现"仅在桌面显示"，支持多显示器

import ctypes
from ctypes import wintypes

import win32gui
import win32con
import win32process

# Windows API 常量
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000

SMTO_NORMAL = 0x0000

# 窗口类名
SHELLDLL_DefView_WindowName = "SHELLDLL_DefView"
WorkerW_WindowName = "WorkerW"
Progman_WindowName = "Progman"


def get_desktop_workerw():
    """
    获取正确的桌面 WorkerW（空的那个，不包含 SHELLDLL_DefView）
    这才是桌面背景层，桌宠应该挂到这里
    """
    progman = win32gui.FindWindow(Progman_WindowName, None)
    if not progman:
        return None

    # 触发 WorkerW 创建
    win32gui.SendMessageTimeout(
        progman,
        0x052C,  # 触发 WorkerW 创建的消息
        0,
        0,
        SMTO_NORMAL,
        1000,
    )

    workerw = None

    def enum_callback(hwnd, _):
        nonlocal workerw
        # 检查这个 WorkerW 是否包含 SHELLDLL_DefView
        shell = win32gui.FindWindowEx(hwnd, None, SHELLDLL_DefView_WindowName, None)
        if shell:
            # 找到图标层后，获取它后面的那个 WorkerW（空的）
            workerw = win32gui.FindWindowEx(None, hwnd, WorkerW_WindowName, None)
        return True

    win32gui.EnumWindows(enum_callback, None)

    return workerw


def attach_to_desktop(hwnd):
    """
    将窗口挂载到桌面 WorkerW
    实现"仅在桌面显示"效果
    """
    try:
        # 获取正确的桌面 WorkerW
        workerw = get_desktop_workerw()

        if not workerw:
            # print("无法找到桌面 WorkerW")
            return False

        # 移除窗口原有的父窗口
        current_parent = win32gui.GetParent(hwnd)
        if current_parent:
            win32gui.SetParent(hwnd, 0)

        # 设置为 WorkerW 的子窗口
        win32gui.SetParent(hwnd, workerw)

        # 设置为底部（确保在其他窗口下面）
        ctypes.windll.user32.SetWindowPos(
            hwnd,
            win32con.HWND_BOTTOM,
            0,
            0,
            0,
            0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
        )

        return True
    except Exception as e:
        print(f"挂载到桌面失败: {e}")
        return False


def detach_from_desktop(hwnd):
    """
    从 WorkerW 分离，恢复为顶层窗口
    """
    try:
        current_parent = win32gui.GetParent(hwnd)

        if current_parent:
            class_name = win32gui.GetClassName(current_parent)
            if class_name == WorkerW_WindowName:
                win32gui.SetParent(hwnd, 0)

        return True
    except Exception as e:
        print(f"从桌面分离失败: {e}")
        return False


def set_window_exstyle(hwnd, add_style, remove_style=0):
    """修改窗口扩展样式"""
    try:
        current_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

        if add_style:
            current_style |= add_style
        if remove_style:
            current_style &= ~remove_style

        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, current_style)

        # 强制刷新窗口
        win32gui.SetWindowPos(
            hwnd,
            0,
            0,
            0,
            0,
            0,
            win32con.SWP_NOMOVE
            | win32con.SWP_NOSIZE
            | win32con.SWP_NOZORDER
            | win32con.SWP_FRAMECHANGED,
        )
    except Exception as e:
        print(f"设置窗口样式失败: {e}")


def make_tool_window(hwnd):
    """将窗口设置为工具窗口（不显示在任务栏）"""
    set_window_exstyle(hwnd, WS_EX_TOOLWINDOW)


def remove_app_window(hwnd):
    """移除窗口在任务栏的显示"""
    set_window_exstyle(hwnd, 0, WS_EX_APPWINDOW)


def enable_click_through(hwnd):
    """启用点击穿透"""
    set_window_exstyle(hwnd, WS_EX_LAYERED | WS_EX_TRANSPARENT)


def disable_click_through(hwnd):
    """禁用点击穿透"""
    set_window_exstyle(hwnd, 0, WS_EX_TRANSPARENT)


def ensure_bottom(hwnd):
    """确保窗口在 WorkerW 中保持底部"""
    try:
        parent = win32gui.GetParent(hwnd)
        if parent:
            class_name = win32gui.GetClassName(parent)
            if class_name == WorkerW_WindowName:
                ctypes.windll.user32.SetWindowPos(
                    hwnd,
                    win32con.HWND_BOTTOM,
                    0,
                    0,
                    0,
                    0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
                )
    except Exception:
        pass


def is_window_on_desktop(hwnd):
    """检查窗口是否已经挂载到桌面"""
    try:
        parent = win32gui.GetParent(hwnd)
        if parent:
            class_name = win32gui.GetClassName(parent)
            return class_name == WorkerW_WindowName
        return False
    except Exception:
        return False
