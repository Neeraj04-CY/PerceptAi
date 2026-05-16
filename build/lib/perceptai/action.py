import pyautogui
import pyperclip
import time

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.3


def click(x, y, double=False):
    try:
        pyautogui.moveTo(x, y, duration=0.2)
        if double:
            pyautogui.doubleClick(x, y)
        else:
            pyautogui.click(x, y)
        time.sleep(0.3)
        return {"success": True, "action": "click", "position": {"x": x, "y": y}}
    except Exception as e:
        return {"success": False, "error": str(e)}


def type_text(text, use_clipboard=True):
    """
    Types text reliably.
    Uses clipboard paste for special characters — works on everything.
    """
    try:
        if use_clipboard:
            # Save current clipboard
            try:
                previous = pyperclip.paste()
            except Exception:
                previous = ""

            # Paste via clipboard — handles ALL characters
            pyperclip.copy(text)
            time.sleep(0.1)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.2)

            return {"success": True, "action": "type", "text": text, "method": "clipboard"}
        else:
            # Fallback to typewrite for simple ASCII
            pyautogui.typewrite(text, interval=0.04)
            return {"success": True, "action": "type", "text": text, "method": "typewrite"}

    except Exception as e:
        return {"success": False, "error": str(e)}


def clear_and_type(text):
    """Select all existing text and replace with new text"""
    try:
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.2)
        return type_text(text)
    except Exception as e:
        return {"success": False, "error": str(e)}


def scroll(x, y, direction="down", amount=3):
    try:
        pyautogui.moveTo(x, y, duration=0.1)
        clicks = -amount if direction == "down" else amount
        pyautogui.scroll(clicks)
        return {"success": True, "action": "scroll", "direction": direction}
    except Exception as e:
        return {"success": False, "error": str(e)}


def hotkey(*keys):
    try:
        pyautogui.hotkey(*keys)
        return {"success": True, "action": "hotkey", "keys": keys}
    except Exception as e:
        return {"success": False, "error": str(e)}


def right_click(x, y):
    try:
        pyautogui.rightClick(x, y)
        return {"success": True, "action": "right_click", "position": {"x": x, "y": y}}
    except Exception as e:
        return {"success": False, "error": str(e)}
