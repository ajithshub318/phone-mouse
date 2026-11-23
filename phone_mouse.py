"""phone-mouse: use your Android phone like a second monitor for your mouse and keyboard.

Phone on the USB cable with USB debugging on; scrcpy pushes its helper to the phone by itself.
Run:  python phone_mouse.py        Self-check:  python phone_mouse.py --test
"""
import ctypes, ctypes.wintypes as wt, glob, json, os, queue, shutil, subprocess, sys, threading, time
import tkinter as tk
from pathlib import Path

u32 = ctypes.windll.user32
HERE = Path(__file__).resolve().parent
CONFIG = HERE / "config.json"
SHOTS = Path.home() / "Pictures" / "PhoneMouse"
PHONE_SHOTS = "/sdcard/Pictures/Screenshots/* /sdcard/DCIM/Screenshots/*"  # stock Android, Samsung
# scale = phone pixels per mouse count; return_push = counts you push past the phone edge to come back.
# ponytail: Android adds its own pointer acceleration, so `scale` is a tuning knob, not a law.
DEFAULTS = {"side": "right", "scale": 1.0, "return_push": 40}
NOWIN = 0x08000000  # CREATE_NO_WINDOW: no console flashes for adb
LOG = HERE / "debug.log"


def log(*a):
    with open(LOG, "a") as f:
        print(time.strftime("%H:%M:%S"), *a, file=f)


# ---------- pure logic (covered by --test) ----------

def step(x, push, dx, width, side, scale, need):
    """Move the phone-pointer estimate by one raw mouse delta. Returns (x, push, leave_phone)."""
    raw = x + dx * scale
    x = min(max(raw, 0), width)
    over = ((x - raw) if side == "right" else (raw - x)) / scale  # counts pushed past the PC-side edge
    if over > 0:
        push += over
    elif not (dx == 0 and x == (0 if side == "right" else width)):
        push = 0
    return x, push, push >= need


def selftest():
    x, p, out = step(0, 0, 50, 1000, "right", 1.0, 40)
    assert (x, p, out) == (50, 0, False)
    x, p, out = step(x, p, -80, 1000, "right", 1.0, 40)       # hits the left edge, 30 past it
    assert (x, p, out) == (0, 30, False)
    x, p, out = step(x, p, 0, 1000, "right", 1.0, 40)         # vertical-only move keeps the push
    assert (x, p, out) == (0, 30, False)
    assert step(x, p, -10, 1000, "right", 1.0, 40)[2]         # 40 past the edge -> back to PC
    assert step(0, 30, 5, 1000, "right", 1.0, 40)[:2] == (5, 0)  # moving away resets the push
    assert step(1000, 0, 60, 1000, "left", 1.0, 40)[2]        # phone on the left: exit on its right edge
    print("ok")


# ---------- Windows helpers ----------

class RECT(ctypes.Structure):
    _fields_ = [("l", wt.LONG), ("t", wt.LONG), ("r", wt.LONG), ("b", wt.LONG)]

u32.FindWindowW.restype = wt.HWND
u32.GetForegroundWindow.restype = wt.HWND
u32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]


def monitors():
    out = []
    CB = ctypes.WINFUNCTYPE(wt.BOOL, wt.HMONITOR, wt.HDC, ctypes.POINTER(RECT), wt.LPARAM)
    cb = CB(lambda h, dc, r, lp: out.append((r.contents.l, r.contents.t, r.contents.r, r.contents.b)) or True)
    u32.EnumDisplayMonitors(None, None, cb, 0)
    return out


def cursor():
    p = wt.POINT(); u32.GetCursorPos(ctypes.byref(p)); return p.x, p.y


MARK = 0x504D  # dwExtraInfo on moves we inject, so the raw listener can ignore them


def click():
    u32.mouse_event(0x0002, 0, 0, 0, 0); u32.mouse_event(0x0004, 0, 0, 0, 0)


def tap_alt():
    u32.keybd_event(0x12, 0, 0, 0); u32.keybd_event(0x12, 0, 2, 0)


def key_down(vk):
    return u32.GetAsyncKeyState(vk) & 0x8000


def make_invisible(h):
    # scrcpy only needs its window for capturing the mouse; make it see-through and keep it off the taskbar
    u32.ShowWindow(h, 0)
    u32.SetWindowLongW(h, -20, u32.GetWindowLongW(h, -20) | 0x80000 | 0x80)  # WS_EX_LAYERED | WS_EX_TOOLWINDOW
    u32.SetLayeredWindowAttributes(h, 0, 1, 2)  # alpha 1/255: invisible but still clickable
    park(h)
    u32.ShowWindow(h, 4)  # SW_SHOWNOACTIVATE


def park(h):
    u32.SetWindowPos(h, None, -32000, -32000, 0, 0, 0x1 | 0x4 | 0x10)


def place(h, x, y):
    u32.SetWindowPos(h, wt.HWND(-1), x, y, 0, 0, 0x1 | 0x40)  # topmost, keep size, show


# ---------- raw mouse deltas (what scrcpy forwards to the phone) ----------

class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wt.DWORD), ("dwSize", wt.DWORD), ("hDevice", wt.HANDLE), ("wParam", wt.WPARAM)]

class RAWMOUSE(ctypes.Structure):
    _fields_ = [("usFlags", wt.USHORT), ("_pad", wt.USHORT), ("usButtonFlags", wt.USHORT),
                ("usButtonData", wt.USHORT), ("ulRawButtons", wt.ULONG), ("lLastX", wt.LONG),
                ("lLastY", wt.LONG), ("ulExtraInformation", wt.ULONG)]

class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("mouse", RAWMOUSE)]

class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wt.USHORT), ("usUsage", wt.USHORT), ("dwFlags", wt.DWORD), ("hwndTarget", wt.HWND)]

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR)]


def raw_mouse_loop(sink):
    """Background thread: push every real mouse/touchpad delta (dx, dy) into `sink`. Our own moves are skipped."""
    u32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    u32.DefWindowProcW.restype = ctypes.c_ssize_t
    u32.GetRawInputData.argtypes = [wt.HANDLE, wt.UINT, ctypes.c_void_p, ctypes.POINTER(wt.UINT), wt.UINT]
    u32.GetRawInputData.restype = wt.UINT
    u32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
    u32.CreateWindowExW.restype = wt.HWND

    def proc(h, msg, wp, lp):
        if msg == 0x00FF:  # WM_INPUT
            ri = RAWINPUT(); size = wt.UINT(ctypes.sizeof(ri))
            ok = u32.GetRawInputData(lp, 0x10000003, ctypes.byref(ri), ctypes.byref(size),
                                     ctypes.sizeof(RAWINPUTHEADER)) != 0xFFFFFFFF
            # touchpads report hDevice=0, so skip our own moves by their marker, not by device
            if ok and ri.header.dwType == 0 and ri.mouse.ulExtraInformation != MARK and not ri.mouse.usFlags & 1:
                sink.put((ri.mouse.lLastX, ri.mouse.lLastY))
        return u32.DefWindowProcW(h, msg, wp, lp)

    wndproc = WNDPROC(proc)
    u32.RegisterClassW(ctypes.byref(WNDCLASSW(lpfnWndProc=wndproc, lpszClassName="PhoneMouseRaw")))
    hwnd = u32.CreateWindowExW(0, "PhoneMouseRaw", None, 0, 0, 0, 0, 0, wt.HWND(-3), None, None, None)
    dev = RAWINPUTDEVICE(1, 2, 0x100, hwnd)  # mouse, RIDEV_INPUTSINK (works while other apps have focus)
    u32.RegisterRawInputDevices(ctypes.byref(dev), 1, ctypes.sizeof(dev))
    msg = wt.MSG()
    while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        u32.TranslateMessage(ctypes.byref(msg)); u32.DispatchMessageW(ctypes.byref(msg))


# ---------- adb / scrcpy ----------

def find_scrcpy():
    hits = glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Genymobile.scrcpy*\*\scrcpy.exe"))
    exe = shutil.which("scrcpy") or (hits[0] if hits else None)
    if not exe:
        sys.exit("scrcpy not found. Install it:  winget install Genymobile.scrcpy")
    return exe

SCRCPY = ADB = None


def adb(*args):
    try:
        return subprocess.run([ADB, *args], capture_output=True, text=True, creationflags=NOWIN, timeout=15).stdout
    except Exception:
        return ""


def phone_size():
    try:
        w, h = adb("shell", "wm", "size").strip().splitlines()[-1].split()[-1].split("x")
        return int(w), int(h)
    except Exception:
        return 1080, 2400


def watch_screenshots(q):
    """Background thread: put the phone path of every new screenshot into `q`."""
    last = None
    while True:
        name = adb("shell", f"ls -td {PHONE_SHOTS} 2>/dev/null | head -1").strip()
        if name and last is not None and name != last:
            q.put(name)
        last = name or last
        time.sleep(2)


# ---------- screenshot drawing window ----------

class Sketch:
    COLORS = ["#ff3b30", "#ffcc00", "#34c759", "#0a84ff", "#000000", "#ffffff"]

    def __init__(self, root, path, app):
        from PIL import Image
        self.app = app
        self.path, self.img, self.undo, self.color = path, Image.open(path).convert("RGB"), [], self.COLORS[0]
        self.k = min(1.0, root.winfo_screenheight() * 0.78 / self.img.height)
        self.w = tk.Toplevel(root); self.w.title(f"Phone screenshot - {path.name}")
        bar = tk.Frame(self.w); bar.pack(fill="x")
        for c in self.COLORS:
            tk.Button(bar, bg=c, activebackground=c, width=2, command=lambda c=c: self.pick(c)).pack(side="left", padx=2, pady=4)
        for text, fn in (("Undo", self.do_undo), ("Copy", self.copy), ("Save", self.save)):
            tk.Button(bar, text=text, command=fn).pack(side="left", padx=4)
        self.msg = tk.Label(bar, text="Draw with the mouse"); self.msg.pack(side="left", padx=8)
        self.cv = tk.Canvas(self.w, width=int(self.img.width * self.k), height=int(self.img.height * self.k),
                            highlightthickness=0, cursor="crosshair")
        self.cv.pack()
        self.cv.bind("<ButtonPress-1>", self.down)
        self.cv.bind("<B1-Motion>", self.move)
        self.cv.bind("<ButtonRelease-1>", lambda e: self.render())
        self.w.bind("<Control-z>", lambda e: self.do_undo())
        self.w.bind("<Control-c>", lambda e: self.copy())
        self.w.bind("<Control-s>", lambda e: self.save())
        self.render(); self.w.lift(); self.w.focus_force()

    def render(self):
        from PIL import ImageTk
        size = (int(self.img.width * self.k), int(self.img.height * self.k))
        self.photo = ImageTk.PhotoImage(self.img.resize(size))
        self.cv.delete("all"); self.cv.create_image(0, 0, image=self.photo, anchor="nw")

    def pick(self, c):
        self.color = c

    def down(self, e):
        self.undo = (self.undo + [self.img.copy()])[-20:]
        self.last = (e.x, e.y); self.move(e)

    def move(self, e):
        from PIL import ImageDraw
        r = 3 / self.k  # pen radius in full-size pixels (6px wide on screen)
        x0, y0, x1, y1 = self.last[0] / self.k, self.last[1] / self.k, e.x / self.k, e.y / self.k
        d = ImageDraw.Draw(self.img)
        d.line([(x0, y0), (x1, y1)], fill=self.color, width=int(2 * r))
        d.ellipse([x1 - r, y1 - r, x1 + r, y1 + r], fill=self.color)  # round joints, no gaps
        self.cv.create_line(*self.last, e.x, e.y, fill=self.color, width=6, capstyle="round")
        self.last = (e.x, e.y)

    def do_undo(self):
        if self.undo:
            self.img = self.undo.pop(); self.render()

    def save(self):
        out = self.path.with_name(self.path.stem + "-drawn.png")
        self.img.save(out); self.msg.config(text=f"Saved {out}")
        return out

    def copy(self):
        out = self.save()
        self.app.ignore_clip_until = time.time() + 4  # don't pop up for our own copy
        p = str(out).replace("'", "''")
        subprocess.Popen(["powershell", "-NoProfile", "-STA", "-Command",
                          "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
                          f"[System.Windows.Forms.Clipboard]::SetImage([System.Drawing.Image]::FromFile('{p}'))"],
                         creationflags=NOWIN)
        self.msg.config(text="Copied to clipboard (also saved)")


# ---------- main app: layout window + edge switching ----------

class App:
    def __init__(self):
        self.cfg = dict(DEFAULTS)
        if CONFIG.exists():
            self.cfg.update(json.loads(CONFIG.read_text()))
        self.mons = monitors()
        self.L = min(m[0] for m in self.mons); self.T = min(m[1] for m in self.mons)
        self.R = max(m[2] for m in self.mons); self.B = max(m[3] for m in self.mons)
        self.pw, self.ph = 1080, 2400
        self.proc = self.hwnd = None
        self.next_try = 0
        self.state, self.cool, self.est, self.push, self.entry_y, self.entered = "pc", 0, 0, 0, 0, 0
        self.sending_alt = False
        self.held = None
        self.clip_seq, self.ignore_clip_until, self.next_clip_check = u32.GetClipboardSequenceNumber(), 0, 0
        self.deltas, self.shots = queue.Queue(), queue.Queue()
        threading.Thread(target=raw_mouse_loop, args=(self.deltas,), daemon=True).start()
        threading.Thread(target=watch_screenshots, args=(self.shots,), daemon=True).start()

        self.root = tk.Tk(); self.root.title("Phone Mouse"); self.root.resizable(False, False)
        tk.Label(self.root, text="Drag the phone to the side of your screen where it sits.",
                 font=("Segoe UI", 10)).pack(padx=12, pady=(10, 4))
        self.cv = tk.Canvas(self.root, width=560, height=240, bg="#f4f4f4", highlightthickness=0)
        self.cv.pack(padx=12)
        self.status = tk.Label(self.root, text="Looking for the phone on USB...", font=("Segoe UI", 9), fg="#555")
        self.status.pack(padx=12, pady=(4, 2))
        tk.Label(self.root, text="Swipe on the phone: drag with the mouse, or Ctrl+Shift+Left / Right.  "
                                 "Alt = back to PC.  Phone screenshots pop up here to draw on.",
                 font=("Segoe UI", 8), fg="#777", wraplength=540).pack(padx=12, pady=(0, 10))
        # press on the phone, then follow the mouse on the whole canvas (the box is redrawn while dragging)
        self.dragging = False
        self.cv.tag_bind("phone", "<ButtonPress-1>", lambda e: setattr(self, "dragging", True))
        self.cv.bind("<B1-Motion>", self.drag)
        self.cv.bind("<ButtonRelease-1>", self.drop)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.draw_layout()
        self.root.after(10, self.tick)
        self.root.mainloop()

    # layout

    def draw_layout(self, phone_x=None):
        cv = self.cv; cv.delete("all")
        vw, vh = self.R - self.L, self.B - self.T
        edge_h = max(m[3] - m[1] for m in self.mons)
        ph_h = edge_h * 0.7; ph_w = ph_h * self.pw / self.ph
        s = min(500 / (vw + 2 * ph_w + 80), 200 / vh)
        self.s, self.ox, self.oy = s, 280 - vw * s / 2, 120 - vh * s / 2
        for i, (l, t, r, b) in enumerate(self.mons, 1):
            x0, y0 = self.ox + (l - self.L) * s, self.oy + (t - self.T) * s
            cv.create_rectangle(x0, y0, x0 + (r - l) * s, y0 + (b - t) * s, fill="#cfe3ff", outline="#3b7ddd", width=2)
            cv.create_text(x0 + (r - l) * s / 2, y0 + (b - t) * s / 2, text=f"Screen {i}", font=("Segoe UI", 10))
        w, h = ph_w * s, ph_h * s
        if phone_x is None:
            phone_x = self.ox + vw * s + 10 if self.cfg["side"] == "right" else self.ox - 10 - w
        y = 120 - h / 2
        cv.create_rectangle(phone_x, y, phone_x + w, y + h, fill="#222", outline="#000", width=2, tags="phone")
        cv.create_text(phone_x + w / 2, y + h / 2, text="Phone", fill="white", font=("Segoe UI", 9), tags="phone")
        self.phone_w = w

    def drag(self, e):
        if self.dragging:
            self.draw_layout(phone_x=e.x - self.phone_w / 2)

    def drop(self, e):
        if not self.dragging:
            return
        self.dragging = False
        self.cfg["side"] = "left" if e.x < 280 else "right"
        CONFIG.write_text(json.dumps(self.cfg, indent=2))
        self.draw_layout()
        self.status.config(text=f"Phone is on the {self.cfg['side']}. Move the cursor off the {self.cfg['side']} edge.")

    # main loop

    def tick(self):
        try:
            self.update()
        finally:
            self.root.after(8, self.tick)

    def update(self):
        now = time.time()
        if now > self.next_clip_check:  # works even without a phone
            self.next_clip_check = now + 0.5
            self.check_pc_screenshot()
        if self.proc is None or self.proc.poll() is not None:
            if self.hwnd:
                self.status.config(text="Phone disconnected. Plug it in by USB...")
            self.hwnd, self.state = None, "pc"
            if now > self.next_try:
                self.next_try = now + 3
                self.proc = subprocess.Popen(
                    [SCRCPY, "--no-video", "--no-audio", "--mouse=uhid", "--keyboard=uhid", "--window-borderless",
                     "--window-title=PhoneMouse", "--window-width=200", "--window-height=200"],
                    creationflags=NOWIN, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        if not self.hwnd:
            h = u32.FindWindowW(None, "PhoneMouse")
            if h:
                self.hwnd = h; make_invisible(h)
                self.pw, self.ph = phone_size(); self.draw_layout()
                model = adb("shell", "getprop", "ro.product.model").strip() or "phone"
                self.status.config(text=f"Connected: {model}. Move the cursor off the {self.cfg['side']} edge.")
            return

        while not self.shots.empty():
            name = self.shots.get()
            self.popup("New phone screenshot", lambda name=name: self.open_shot(name))

        key = None  # Ctrl+Shift+Left / Right = swipe
        if key_down(0x11) and key_down(0x10):
            key = "L" if key_down(0x25) else "R" if key_down(0x27) else None
        if key and key != self.held:
            self.swipe(key == "L")
        self.held = key

        right = self.cfg["side"] == "right"
        if self.state == "pc":
            while not self.deltas.empty():
                self.deltas.get()
            x, y = cursor()
            if now > self.cool and (x >= self.R - 1 if right else x <= self.L):
                self.enter(y)
        elif self.state == "phone":
            while not self.deltas.empty():
                dx, _ = self.deltas.get()
                self.est, self.push, leave = step(self.est, self.push, dx, self.pw, self.cfg["side"],
                                                  self.cfg["scale"], self.cfg["return_push"])
                if leave:
                    return self.leave()
            if now - self.entered > 0.5 and not self.sending_alt and (
                    key_down(0x12) or u32.GetForegroundWindow() != self.hwnd):
                self.released()  # you pressed Alt (scrcpy lets go) or switched windows

    def enter(self, y):
        right = self.cfg["side"] == "right"
        wx = self.R - 220 if right else self.L + 20
        wy = min(max(y - 100, self.T), self.B - 200)
        self.entry_y, self.entered, self.state = y, time.time(), "phone"
        log("enter at y", y)
        place(self.hwnd, wx, wy)
        u32.SetForegroundWindow(self.hwnd)
        u32.SetCursorPos(wx + 100, wy + 100)
        click()  # clicking scrcpy's window makes it grab the mouse; the phone pointer appears
        self.root.after(150, self.slam)

    def slam(self):
        # push the phone pointer hard against the edge you came in from, so we know where it is
        right = self.cfg["side"] == "right"
        for _ in range(30):
            u32.mouse_event(0x0001, -127 if right else 127, 0, 0, MARK)
        self.est, self.push = (0 if right else self.pw), 0
        while not self.deltas.empty():
            self.deltas.get()

    def leave(self):
        log("leave: pushed past the edge")
        self.sending_alt, self.state = True, "leaving"
        tap_alt()  # scrcpy releases the mouse on Alt
        self.root.after(80, self.back_on_pc, 3)

    def released(self):
        log("released: alt", bool(key_down(0x12)), "fg_is_scrcpy", u32.GetForegroundWindow() == self.hwnd)
        self.state = "leaving"
        self.root.after(80, self.back_on_pc, 60)

    def back_on_pc(self, inset):
        park(self.hwnd)
        x = self.R - 1 - inset if self.cfg["side"] == "right" else self.L + inset
        u32.SetCursorPos(x, self.entry_y)
        self.state, self.sending_alt, self.cool = "pc", False, time.time() + 0.3

    def swipe(self, left):
        a, b = (self.pw * 4 // 5, self.pw // 5) if left else (self.pw // 5, self.pw * 4 // 5)
        subprocess.Popen([ADB, "shell", "input", "swipe", str(a), str(self.ph // 2), str(b), str(self.ph // 2), "150"],
                         creationflags=NOWIN)

    # screenshots

    def check_pc_screenshot(self):
        # PrtScn / Win+Shift+S put an image on the clipboard; offer to draw on it
        seq = u32.GetClipboardSequenceNumber()
        if seq == self.clip_seq:
            return
        self.clip_seq = seq
        if time.time() < self.ignore_clip_until:
            return  # our own Copy button
        from PIL import ImageGrab, Image
        try:
            img = ImageGrab.grabclipboard()
        except Exception:
            return
        if isinstance(img, Image.Image):
            SHOTS.mkdir(parents=True, exist_ok=True)
            path = SHOTS / time.strftime("PC_%Y%m%d-%H%M%S.png")
            img.save(path)
            self.popup("New PC screenshot", lambda: Sketch(self.root, path, self))

    def popup(self, title, on_open):
        t = tk.Toplevel(self.root); t.overrideredirect(True); t.attributes("-topmost", True)
        bg = "#1f1f1f"; t.configure(bg=bg)
        tk.Label(t, text=title, fg="white", bg=bg, font=("Segoe UI", 11, "bold")).pack(
            padx=14, pady=(12, 6), anchor="w")
        row = tk.Frame(t, bg=bg); row.pack(padx=14, pady=(0, 12), anchor="w")
        tk.Button(row, text="Open and draw", command=lambda: (t.destroy(), on_open())).pack(side="left")
        tk.Button(row, text="Dismiss", command=t.destroy).pack(side="left", padx=6)
        t.update_idletasks()
        t.geometry(f"+{self.root.winfo_screenwidth() - t.winfo_width() - 24}"
                   f"+{self.root.winfo_screenheight() - t.winfo_height() - 80}")
        t.after(15000, lambda: t.winfo_exists() and t.destroy())

    def open_shot(self, name):
        SHOTS.mkdir(parents=True, exist_ok=True)
        dest = SHOTS / name.rsplit("/", 1)[-1]
        adb("pull", name, str(dest))
        if dest.exists():
            Sketch(self.root, dest, self)
        else:
            self.status.config(text=f"Couldn't copy {name} from the phone.")

    def quit(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.root.destroy()


if __name__ == "__main__":
    if "--test" in sys.argv:
        selftest(); sys.exit()
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # real pixel coordinates on scaled displays
    SCRCPY = find_scrcpy()
    ADB = shutil.which("adb") or os.path.join(os.path.dirname(SCRCPY), "adb.exe")
    App()
