# Receiver Setup

The receiver is a small background program that runs silently on each device where you want audio to play. It connects to the hub and plays sound when someone talks.

You install it once per device. After that it starts automatically when you log in.

---

## What you'll need before starting

- The IP address of your hub (e.g. `192.168.1.10`). Find it by opening the admin page on the device running the hub: `http://<hub-device>:8000/admin`
- A name for this receiver — pick something descriptive like `Living Room`, `Office`, or `Kitchen`

---

## Windows

### 1. Download

Go to the [Releases page](https://github.com/RNCDev/intrakom/releases/latest) and download `intrakom-receiver-windows-x64.zip`.

### 2. Unzip

Right-click the zip file → **Extract All** → choose a permanent location like `C:\Program Files\Intrakom\` or `C:\Users\YourName\Intrakom\`.

> **Important:** Don't run install.bat from inside the zip — extract it first.

### 3. Install

Double-click `install.bat`.

It will ask you two questions:
1. **Receiver name** — what to call this room (e.g. `Living Room`)
2. **Hub URL** — the address of your hub (e.g. `http://192.168.1.10:8000`)

Type each answer and press Enter.

### 4. Verify

Open a browser and go to `http://<hub-ip>:8000/admin`. Your receiver's name should appear in the table with status **online**.

If it doesn't appear within 30 seconds, see [Troubleshooting](troubleshooting.md).

### Uninstall

Double-click `uninstall.bat` in the same folder.

---

## macOS

### 1. Download

Go to the [Releases page](https://github.com/RNCDev/intrakom/releases/latest) and download `intrakom-receiver-macos-arm64.zip`.

### 2. Unzip and move

Double-click the zip to unzip it. Move the resulting folder to a permanent location like `~/Applications/Intrakom/` or `/Applications/Intrakom/`.

### 3. Install

Double-click `install.command` in Finder. A Terminal window will open and walk you through setup.

It will ask you two questions:
1. **Receiver name** — what to call this room (e.g. `Living Room`)
2. **Hub URL** — the address of your hub (e.g. `http://192.168.1.10:8000`)

Type each answer and press Enter.

### 5. Verify

Open a browser and go to `http://<hub-ip>:8000/admin`. Your receiver's name should appear with status **online**.

### Uninstall

Double-click `uninstall.sh` in Finder, or run `./uninstall.sh` in Terminal.

---

## Linux / Raspberry Pi (as a receiver)

If you want a Raspberry Pi or Linux box to act as a receiver (playing audio through its speakers):

### Using .deb (recommended)

```bash
sudo dpkg -i intrakom-receiver_*.deb
```

Then set your receiver name and hub URL:
```bash
sudo nano /etc/default/intrakom-receiver
```

Add:
```
RECEIVER_NAME="Living Room"
HUB_URL="http://192.168.1.10:8000"
```

Then start it:
```bash
sudo systemctl enable --now intrakom-receiver
```

### Verify

```bash
sudo systemctl status intrakom-receiver
```

---

## Running multiple receivers on one machine

If you have one machine with multiple audio outputs (e.g. bedroom speakers and living room speakers), you can run multiple receivers by installing with different names. Run `install.bat` (Windows) or `install.command` (macOS) again with a different name — each instance is registered as a separate scheduled task / launchd agent.

> Note: On Windows, each additional receiver needs a unique Task Scheduler task name. The install script names the task `Intrakom Receiver`. For a second one, edit `install.bat` and change the `/TN` value before running.
