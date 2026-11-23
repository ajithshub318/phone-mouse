# phone-mouse

Push your Windows cursor off the right edge of the screen and your mouse and keyboard move to your Android phone. Press **Alt** to bring them back.

It's a small Python script built on [scrcpy](https://github.com/Genymobile/scrcpy). scrcpy's `uhid` mode makes the phone see your PC mouse and keyboard as real USB devices, and the script switches over to the phone when the cursor reaches the screen edge.

## Requirements

- Windows
- Python 3
- scrcpy: `winget install Genymobile.scrcpy`
- An Android phone with USB debugging on, showing as `device` in `adb devices` (USB or Wi-Fi adb)

## Use

```
python phone_mouse.py
```

or double-click `run.bat`.

1. A small "PhoneMouse" window opens in the bottom-right corner.
2. Push the cursor past the right edge of the screen. A pointer appears on the phone and your keyboard types on the phone.
3. Press **Alt** to get your mouse back on the PC.
4. Close the window or press Ctrl+C to quit.

## Limits

- The phone's pointer starts where it was last time, not at its left edge.
- To come back you press Alt. Pushing past the phone's left edge doesn't bring the mouse back, because the phone doesn't report where its pointer is.
- The right edge of your rightmost monitor is the edge that triggers the switch.
- It works with one connected phone.

You can change `EDGE_PX`, `REARM_PX` and the window size at the top of `phone_mouse.py`.

## License

MIT
