import os
import sys
import json
import time

sys.path.insert(0, os.path.join(os.getcwd(), 'api'))
sys.path.insert(0, os.path.join(os.getcwd(), 'core'))

from api.executor import execute_task
import agent as agent_mod
import action as action_mod
import os_control as os_mod


def safe(msg):
    return msg.encode('ascii', 'backslashreplace').decode('ascii')

def log(msg):
    print(safe(msg))

orig_popen = os_mod.subprocess.Popen
orig_open_app = agent_mod.open_app
orig_focus_window = agent_mod.focus_window
orig_type_text = agent_mod.type_text
orig_clear_and_type = agent_mod.clear_and_type
orig_click = action_mod.click
orig_hotkey = action_mod.pyautogui.hotkey
orig_press = action_mod.pyautogui.press
orig_moveTo = action_mod.pyautogui.moveTo
orig_doubleClick = action_mod.pyautogui.doubleClick
orig_typewrite = action_mod.pyautogui.typewrite


def traced_popen(*args, **kwargs):
    log(f'[subprocess.Popen] args={args!r} kwargs={kwargs!r}')
    return orig_popen(*args, **kwargs)


def traced_open_app(app_name):
    log(f'[agent.open_app] app_name={app_name!r}')
    result = orig_open_app(app_name)
    log(f'[agent.open_app] result={result!r}')
    return result


def traced_focus_window(target):
    log(f'[agent.focus_window] target={target!r}')
    result = orig_focus_window(target)
    log(f'[agent.focus_window] result={result!r}')
    return result


def traced_type_text(text, *args, **kwargs):
    log(f'[agent.type_text] text={text!r} args={args!r} kwargs={kwargs!r}')
    result = orig_type_text(text, *args, **kwargs)
    log(f'[agent.type_text] result={result!r}')
    return result


def traced_clear_and_type(text):
    log(f'[agent.clear_and_type] text={text!r}')
    result = orig_clear_and_type(text)
    log(f'[agent.clear_and_type] result={result!r}')
    return result


def traced_click(x, y, double=False):
    log(f'[action.click] x={x} y={y} double={double}')
    result = orig_click(x, y, double)
    log(f'[action.click] result={result!r}')
    return result


def traced_hotkey(*keys, **kwargs):
    log(f'[pyautogui.hotkey] keys={keys!r} kwargs={kwargs!r}')
    return orig_hotkey(*keys, **kwargs)


def traced_press(*args, **kwargs):
    log(f'[pyautogui.press] args={args!r} kwargs={kwargs!r}')
    return orig_press(*args, **kwargs)


def traced_moveTo(*args, **kwargs):
    log(f'[pyautogui.moveTo] args={args!r} kwargs={kwargs!r}')
    return orig_moveTo(*args, **kwargs)


def traced_doubleClick(*args, **kwargs):
    log(f'[pyautogui.doubleClick] args={args!r} kwargs={kwargs!r}')
    return orig_doubleClick(*args, **kwargs)


def traced_typewrite(*args, **kwargs):
    log(f'[pyautogui.typewrite] args={args!r} kwargs={kwargs!r}')
    return orig_typewrite(*args, **kwargs)

os_mod.subprocess.Popen = traced_popen
agent_mod.open_app = traced_open_app
agent_mod.focus_window = traced_focus_window
agent_mod.type_text = traced_type_text
agent_mod.clear_and_type = traced_clear_and_type
action_mod.click = traced_click
action_mod.pyautogui.hotkey = traced_hotkey
action_mod.pyautogui.press = traced_press
action_mod.pyautogui.moveTo = traced_moveTo
action_mod.pyautogui.doubleClick = traced_doubleClick
action_mod.pyautogui.typewrite = traced_typewrite

print('WINDOWS_BEFORE', json.dumps(os_mod.get_open_windows(), ensure_ascii=True))
start = time.time()
result = execute_task('open chrome and search perceptai')
elapsed = round(time.time() - start, 2)
print('WINDOWS_AFTER', json.dumps(os_mod.get_open_windows(), ensure_ascii=True))
print('RESULT_STATUS', result.get('status'))
print('RESULT_ERROR', result.get('error'))
print('STEP_COUNT', len(result.get('steps', [])))
print('ELAPSED', elapsed)
print('STEPS', json.dumps(result.get('steps', []), indent=2, ensure_ascii=True))
