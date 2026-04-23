# Troubleshooting

---

## Receiver shows "offline" in /admin

The receiver app is not running or cannot reach the hub.

**Check the receiver is running:**

- **Windows**: Open Task Manager → Details tab → look for `intrakom-receiver.exe`
- **macOS**: Open Terminal and run `launchctl list | grep intrakom`
- **Linux**: `sudo systemctl status intrakom-receiver`

**Check the hub URL is correct:**

The receiver needs to connect to the hub's IP address. On the machine running the receiver, try opening the hub URL in a browser: `http://<hub-ip>:8000`. If the sender page doesn't load, the URL is wrong or the hub isn't running.

**Check your firewall:**

On the hub device, make sure port 8000 is open:
- **Linux/Pi**: `sudo ufw allow 8000` (if ufw is active)
- **macOS**: System Settings → Network → Firewall → allow Intrakom

**Reinstall with the correct URL:**

Re-run `install.bat` (Windows) or `install.command` (macOS) with the correct hub URL.

---

## No audio when someone talks

The receiver is connected but nothing plays.

**Check the audio device:**

- Make sure the correct audio output device is selected on the receiver machine
- On Windows: right-click the speaker icon in the taskbar → Sound settings → confirm the correct output device is default
- On macOS: System Settings → Sound → Output

**Check the receiver logs:**

- **Windows**: The receiver logs to `%USERPROFILE%\.intrakom\logs\receiver.log`
- **macOS**: `tail -f ~/Library/Logs/Intrakom/receiver.log`
- **Linux**: `sudo journalctl -u intrakom-receiver -f`

Look for lines starting with `ERROR` — they'll describe the audio problem.

**sounddevice can't open stream:**

If you see `Failed to open audio device`, the audio subsystem may be misconfigured. Try restarting the receiver service:
- Windows: `schtasks /End /TN "Intrakom Receiver"` then `schtasks /Run /TN "Intrakom Receiver"`
- macOS: `launchctl unload ~/Library/LaunchAgents/com.intrakom.receiver.plist && launchctl load ~/Library/LaunchAgents/com.intrakom.receiver.plist`

---

## Sender page says "Offline" or won't connect

**Check the hub is running:**

SSH into your hub device and run:
```bash
sudo systemctl status intrakom-hub
```

If it's not running: `sudo systemctl start intrakom-hub`

**Check you're on the same network:**

The sender and hub must be on the same local network. VPNs can sometimes isolate devices from each other.

**Try the IP address directly:**

Instead of `http://raspberrypi:8000`, try `http://192.168.1.10:8000` (the actual IP). Hostname resolution sometimes fails on some networks.

---

## Microphone permission denied in browser

The sender page now checks microphone permission on load. If access is already blocked, a warning banner appears immediately — you don't need to press a button to find out.

**Chrome/Edge:**
1. Click the lock icon in the address bar
2. Click "Site permissions" or the microphone icon
3. Change Microphone from "Block" to "Allow"
4. Reload the page

**Safari (iOS):**
1. Go to Settings → Safari → Microphone
2. Make sure it's set to "Allow" (not "Deny")
3. Reload the page in Safari

**Firefox:**
1. Click the lock icon in the address bar
2. Click the microphone icon
3. Remove the "Block" permission
4. Reload the page

---

## macOS: "cannot be opened because it is from an unidentified developer"

1. Go to **System Settings → Privacy & Security**
2. Scroll to the Security section
3. You should see a message about Intrakom — click **Allow Anyway**
4. Try double-clicking `install.command` again
5. When prompted "Are you sure you want to open it?", click **Open**

---

## Windows: SmartScreen warning on install.bat

Right-click `install.bat` → **Run as administrator**. If SmartScreen blocks it, click **More info** → **Run anyway**.

---

## Hub starts but mDNS / auto-discovery doesn't work

Receivers can find the hub automatically via mDNS on most networks. If discovery fails, just provide the hub URL explicitly when installing:
```
install.bat "Living Room" http://192.168.1.10:8000
```
or
```bash
./install.command "Living Room" http://192.168.1.10:8000
```

mDNS often fails across Wi-Fi access points or through VLANs. Using the IP address directly is more reliable.

---

## Windows receiver stopped working after a crash

As of v0.2.1 the scheduled task created by `install.bat` restarts automatically on failure (up to 3 times, 1 minute apart). If the receiver crashes more than 3 times before you next log in, restart it manually:

```
schtasks /End /TN "Intrakom Receiver"
schtasks /Run /TN "Intrakom Receiver"
```

Or log out and back in — the task runs at every login.

---

## Receiver shows online in admin but audio doesn't play

As of v0.2.0 the hub sends WebSocket ping frames every 20 seconds. If no pong arrives within 10 seconds the connection is closed and the receiver reconnects automatically. If you see frequent reconnects, check that your network or firewall is not blocking WebSocket keepalive frames.
