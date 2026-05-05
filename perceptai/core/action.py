import pyautogui
import time

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.5

def click(x, y, double=False):
    try:
        if double:
            pyautogui.doubleClick(x, y)
        else:
            pyautogui.click(x, y)
        return {"success": True, "action": "click", "position": {"x": x, "y": y}}
    except Exception as e:
        return {"success": False, "error": str(e)}

def type_text(text, interval=0.05):
    try:
        pyautogui.typewrite(text, interval=interval)
        return {"success": True, "action": "type", "text": text}
    except Exception as e:
        return {"success": False, "error": str(e)}

def scroll(x, y, direction="down", amount=3):
    try:
        clicks = -amount if direction == "down" else amount
        pyautogui.scroll(clicks, x=x, y=y)
        return {"success": True, "action": "scroll", "direction": direction}
    except Exception as e:
        return {"success": False, "error": str(e)}

def hotkey(*keys):
    try:
        pyautogui.hotkey(*keys)
        return {"success": True, "action": "hotkey", "keys": keys}
    except Exception as e:
        return {"success": False, "error": str(e)}
