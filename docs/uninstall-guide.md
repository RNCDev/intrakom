# Full Uninstall — reference for the current deployment

Gitignored. Scope: **Linux hub**, **Windows receiver**, **macOS receiver**.

---

## Linux — Hub (systemd system service)

```bash
# 1. Stop and disable the service
sudo systemctl disable --now intrakom-hub

# 2. Remove the package
sudo apt remove --purge intrakom-hub        # Debian/Ubuntu
# or
sudo dnf remove intrakom-hub                # Fedora/RHEL

# 3. Clean leftover unit file if the package didn't
sudo rm -f /lib/systemd/system/intrakom-hub.service
sudo rm -f /etc/systemd/system/intrakom-hub.service
sudo systemctl daemon-reload

# 4. Firewall rule (only if you added one manually)
sudo ufw delete allow 8000/tcp 2>/dev/null || true

# 5. Verify
systemctl status intrakom-hub 2>&1 | head -3   # should say "could not be found"
ss -tlnp | grep :8000                          # port 8000 should be free
```

---

## Windows — Receiver (zip install, Task Scheduler)

Run in **PowerShell** or cmd.

```powershell
# 1. Stop the running task
schtasks /End /TN "Intrakom Receiver"

# 2. Remove the scheduled task
schtasks /Delete /TN "Intrakom Receiver" /F

# 3. User config
Remove-Item -Recurse -Force "$env:USERPROFILE\.intrakom" -ErrorAction SilentlyContinue

# 4. Delete the install folder (wherever you unzipped it)
# e.g. Remove-Item -Recurse -Force "C:\Users\YourName\Intrakom"

# 5. Verify
schtasks /Query /TN "Intrakom Receiver"   # should say "ERROR: The system cannot find..."
```

---

## macOS — Receiver (zip install, LaunchAgent)

```bash
# 1. Unload and stop the LaunchAgent
launchctl unload ~/Library/LaunchAgents/com.intrakom.receiver.plist 2>/dev/null

# 2. Remove the plist
rm -f ~/Library/LaunchAgents/com.intrakom.receiver.plist

# 3. Logs
rm -rf ~/Library/Logs/Intrakom

# 4. User config
rm -rf ~/.intrakom

# 5. Delete the install folder (wherever you unzipped it)
# e.g. rm -rf ~/Applications/Intrakom

# 6. Verify
launchctl list | grep intrakom   # nothing
```

---

## Notes

- Omit the config/log removal steps if you want to preserve `~/.intrakom` for reinstall.
- On Windows, if you installed multiple receivers (different task names), repeat step 2 for each `/TN`.
