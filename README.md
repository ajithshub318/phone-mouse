# phone-mouse

Use your Android phone like a second monitor for your mouse and keyboard. Put the phone to the left or right of your screen in the layout window. Move the cursor off that edge and it carries on onto the phone. Move it back across the phone's edge and it returns to the PC.

Screenshots you take on the phone pop up on the PC, where you can draw on them, copy them or save them.

Everything runs over the USB cable. [scrcpy](https://github.com/Genymobile/scrcpy) puts its helper on the phone by itself, so you don't install an app on the phone.

## Requirements

- Windows
- Python 3 and Pillow: `pip install pillow`
- scrcpy: `winget install Genymobile.scrcpy`
- An Android phone on a USB cable with USB debugging turned on

## Use

Double-click `run.bat`, or run `python phone_mouse.py`.

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
