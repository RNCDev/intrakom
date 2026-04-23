# Hub Setup

The hub is the router — it receives audio from whoever is talking and forwards it to the right rooms. You install it once on an always-on device (Raspberry Pi, home server, NAS, old laptop).

---

## Prerequisites

- A device that is always on and connected to your home network (Raspberry Pi 4 or newer recommended)
- Python 3.9 or newer
- Git

Check your Python version:
```bash
python3 --version
```

---

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/RNCDev/intrakom.git
cd intrakom
```

### 2. Create a virtual environment and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Start the hub manually (to test)

```bash
python hub.py
```

You should see output like:
```
  ============================================================
  Intercom Server Ready
  LAN URL:      http://192.168.1.10:8000
  Hostname URL: http://pi.local:8000
  TLS:          disabled (no cert)
  mDNS:         enabled
  ============================================================
```

Open that URL in a browser on any device. You should see the sender page.

### 4. Check the admin page

Open `http://<your-pi-ip>:8000/admin` — this shows all connected receivers, their status, and last-seen time. Bookmark it.

---

## Autostart with systemd (so the hub runs on boot)

### 1. Copy the service file

```bash
sudo cp packaging/linux/intrakom-hub.service /lib/systemd/system/
```

### 2. Edit it to point to your install

```bash
sudo nano /lib/systemd/system/intrakom-hub.service
```

Change the `ExecStart` and `WorkingDirectory` lines to match where you cloned the repo:
```ini
[Service]
WorkingDirectory=/home/pi/intrakom
ExecStart=/home/pi/intrakom/venv/bin/python hub.py
```

Also set `User=` to your username (e.g. `pi`).

### 3. Enable and start

```bash
sudo systemctl daemon-reload
sudo systemctl enable intrakom-hub
sudo systemctl start intrakom-hub
```

### 4. Check it's running

```bash
sudo systemctl status intrakom-hub
```

---

## Finding your Pi's IP address

```bash
hostname -I
```

Or look in your router's DHCP table. Give your Pi a static IP in your router so it doesn't change.

---

## Updating

```bash
cd intrakom
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart intrakom-hub
```

---

## Troubleshooting

**Hub starts but I can't reach it from another device**

- Make sure both devices are on the same network (same Wi-Fi or wired LAN)
- Check your Pi's firewall: `sudo ufw status` — if active, allow port 8000: `sudo ufw allow 8000`

**systemd service fails to start**

- Check logs: `sudo journalctl -u intrakom-hub -n 50`
- Make sure the path in `ExecStart` is correct and the venv exists
