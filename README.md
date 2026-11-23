# phone-mouse

Use your Android phone like a second monitor for your mouse and keyboard. Put the phone to the left or right of your screen in the layout window. Move the cursor off that edge and it carries on onto the phone. Move it back across the phone's edge and it returns to the PC.

Screenshots you take on the phone pop up on the PC, where you can draw on them, copy them or save them.

Everything runs over the USB cable. [scrcpy](https://github.com/Genymobile/scrcpy) puts its helper on the phone by itself, so you don't install an app on the phone.

## Install

Download `PhoneMouse-Setup.exe` from [Releases](https://github.com/ajithshub318/phone-mouse/releases) and run it. scrcpy is included, so you don't need Python or anything else. Then open **Phone Mouse** from the Start menu.

On the phone, turn on USB debugging (Settings › About phone › tap "Build number" 7 times, then Developer options › USB debugging). Plug it in with a USB cable and accept the "Allow USB debugging?" prompt.

## Run from source

Needs Python 3, Pillow (`pip install pillow`) and scrcpy (`winget install Genymobile.scrcpy`). Then double-click `run.bat`, or run `python phone_mouse.py`.

To build the installer yourself, install Inno Setup (`winget install JRSoftware.InnoSetup`) and run `.\build.ps1`. The installer is written to `dist\PhoneMouse-Setup.exe`.

## Use

- **Layout:** drag the phone box to the left or right of your screen. The choice is saved in `config.json`.
- **Go to the phone:** move the cursor off that edge of the screen.
- **Come back:** push the pointer past the phone's edge on the PC side, or press **Alt**.
- **Swipe:** drag with the mouse on the phone, or press **Ctrl+Shift+←** / **Ctrl+Shift+→**.
- **Screenshots:** take one on the phone, then click **Open and draw** in the pop-up on the PC. Pick a colour and draw. **Copy** puts the image on the clipboard and **Save** writes it to `Pictures\PhoneMouse`. Ctrl+Z undoes a stroke.

## Tuning

The phone doesn't report where its pointer is, so phone-mouse works it out from your mouse movement. Android speeds the pointer up when you move fast, so if the return to the PC triggers too early or too late, change these in `config.json`:

- `scale`: phone pixels per mouse count (default `1.0`)
- `return_push`: how far you push past the phone's edge to come back (default `40`)

Self-check: `python phone_mouse.py --test`

## License

MIT
