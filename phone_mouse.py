"""Push the cursor past the right screen edge -> mouse + keyboard go to the adb phone.
Press Alt to come back.  Run:  python phone_mouse.py   (Ctrl+C to quit)
"""
import ctypes, glob, os, shutil, subprocess, time

u32 = ctypes.windll.user32
EDGE_PX = 1      # how close to the right edge triggers the switch
REARM_PX = 60    # cursor must move this far back left before the edge fires again
WIN_W, WIN_H = 160, 90

def scrcpy_exe():
    return shutil.which("scrcpy") or glob.glob(os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Genymobile.scrcpy*\*\scrcpy.exe"))[0]

def right_edge():
    # virtual screen = all monitors; ponytail: assumes the phone sits right of the rightmost monitor
    return u32.GetSystemMetrics(76) + u32.GetSystemMetrics(78)  # SM_XVIRTUALSCREEN + SM_CXVIRTUALSCREEN

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

def cursor():
    p = POINT(); u32.GetCursorPos(ctypes.byref(p)); return p.x, p.y

def click_at(x, y):
    u32.SetCursorPos(x, y)
    u32.mouse_event(0x0002, 0, 0, 0, 0)  # left down
    u32.mouse_event(0x0004, 0, 0, 0, 0)  # left up

def main():
    edge = right_edge()
    wx, wy = edge - WIN_W - 10, u32.GetSystemMetrics(1) - WIN_H - 60  # bottom-right, above taskbar
    # uhid = phone sees a real USB mouse/keyboard with its own pointer; clicking the window captures input, Alt releases
    proc = subprocess.Popen([scrcpy_exe(), "--no-video", "--no-audio", "--mouse=uhid", "--keyboard=uhid",
                             "--window-title=PhoneMouse", "--always-on-top",
                             f"--window-x={wx}", f"--window-y={wy}",
                             f"--window-width={WIN_W}", f"--window-height={WIN_H}"])
    print("Ready. Push the cursor off the right edge -> phone. Alt -> back. Ctrl+C to quit.")
    armed = True
    try:
        while proc.poll() is None:
            x, y = cursor()
            if armed and x >= edge - EDGE_PX:
                click_at(wx + WIN_W // 2, wy + WIN_H // 2)  # focus + capture -> mouse now drives the phone
                armed = False
            elif not armed and x < edge - REARM_PX - WIN_W - 20:
                armed = True  # back on the PC side, well away from the edge and the scrcpy box
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()

if __name__ == "__main__":
    main()
