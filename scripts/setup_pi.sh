#!/usr/bin/env bash
# Run ONCE on the Raspberry Pi 4 (Raspberry Pi OS Lite 64-bit, Bookworm) with sudo:
#   sudo bash scripts/setup_pi.sh
# Enables the memory cgroup, installs Docker Engine and tmux, disables automatic updates.
# A reboot is REQUIRED afterwards, then run scripts/check_pi.sh.
set -euo pipefail
CMD=/boot/firmware/cmdline.txt; [ -f "$CMD" ] || CMD=/boot/cmdline.txt
if ! grep -q cgroup_memory=1 "$CMD"; then
  cp "$CMD" "$CMD.bak"
  sed -i '1 s/$/ cgroup_enable=cpuset cgroup_enable=memory cgroup_memory=1/' "$CMD"
  echo "cmdline.txt updated (backup: $CMD.bak)"
fi
apt-get update
apt-get install -y tmux git python3 curl zip
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
usermod -aG docker "${SUDO_USER:-$USER}" || true
systemctl disable --now apt-daily.timer apt-daily-upgrade.timer || true
systemctl enable docker
echo "Model: $(tr -d '\0' < /proc/device-tree/model)"
echo "DONE. Now: sudo reboot, then bash scripts/check_pi.sh"
