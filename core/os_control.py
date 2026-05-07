import subprocess
import pyautogui
import time
import psutil
import os


def open_app(app_name):
    """Open any application by name"""
    app_name_lower = app_name.lower()

    app_paths = {
        "chrome": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Users\neera\AppData\Local\Google\Chrome\Application\chrome.exe"
        ],
        "notepad": r"C:\Windows\System32\notepad.exe",
        "calculator": r"C:\Windows\System32\calc.exe",
        "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "explorer": r"C:\Windows\explorer.exe",
        "wordpad": r"C:\Program Files\Windows NT\Accessories\wordpad.exe"
    }

    try:
        # Direct path launch
        if app_name_lower in app_paths:
            path = app_paths[app_name_lower]
            # Handle multiple possible paths
            if isinstance(path, list):
                for p in path:
                    if os.path.exists(p):
                        subprocess.Popen(p)
                        time.sleep(2)
                        return {"success": True, "app": app_name}
            else:
                if os.path.exists(path):
                    subprocess.Popen(path)
                    time.sleep(2)
                    return {"success": True, "app": app_name}

        # Try Win+R method as fallback
        pyautogui.hotkey('win', 'r')
        time.sleep(0.8)
        pyautogui.typewrite(app_name_lower, interval=0.05)
        pyautogui.press('enter')
        time.sleep(2)
        return {"success": True, "app": app_name, "method": "winR"}

    except Exception as e:
        return {"success": False, "error": str(e)}


def focus_window(window_title_keyword):
    """Bring a window to focus by title keyword"""
    import ctypes

    EnumWindows = ctypes.windll.user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)
    )
    GetWindowText = ctypes.windll.user32.GetWindowTextW
    GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
    IsWindowVisible = ctypes.windll.user32.IsWindowVisible
    SetForegroundWindow = ctypes.windll.user32.SetForegroundWindow

    found_handle = []

    def callback(hwnd, lParam):
        if IsWindowVisible(hwnd):
            length = GetWindowTextLength(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            GetWindowText(hwnd, buff, length + 1)
            if window_title_keyword.lower() in buff.value.lower():
                found_handle.append(hwnd)
        return True

    EnumWindows(EnumWindowsProc(callback), 0)

    if found_handle:
        hwnd = found_handle[0]
        ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        SetForegroundWindow(hwnd)
        time.sleep(0.5)
        return {"success": True, "window": window_title_keyword}

    return {"success": False, "error": f"Window '{window_title_keyword}' not found"}


def get_open_windows():
    """List all currently open visible windows"""
    import ctypes

    EnumWindows = ctypes.windll.user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)
    )
    GetWindowText = ctypes.windll.user32.GetWindowTextW
    GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
    IsWindowVisible = ctypes.windll.user32.IsWindowVisible

    windows = []

    def callback(hwnd, lParam):
        if IsWindowVisible(hwnd):
            length = GetWindowTextLength(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                GetWindowText(hwnd, buff, length + 1)
                windows.append(buff.value)
        return True

    EnumWindows(EnumWindowsProc(callback), 0)
    return windows


def navigate_to_url(url):
    """Open URL directly in default browser"""
    import webbrowser
    webbrowser.open(url)
    time.sleep(2)
    return {"success": True, "url": url}


def get_screen_size():
    """Get actual screen resolution"""
    size = pyautogui.size()
    return {"width": size.width, "height": size.height}
