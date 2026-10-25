#!/usr/bin/env bash
# Checks before the pilot and before the campaign on the Raspberry Pi. Every line must be OK.
source "$(dirname "$0")/load-config.sh"
ok=1
chk() { if eval "$2"; then echo "OK   $1"; else echo "FAIL $1"; ok=0; fi; }
chk "64-bit OS (aarch64)"                 '[ "$(uname -m)" = aarch64 ]'
chk "cgroup v2 controllers cpu+memory"    'grep -q memory /sys/fs/cgroup/cgroup.controllers && grep -q cpu /sys/fs/cgroup/cgroup.controllers'
chk "docker running"                      'docker info >/dev/null 2>&1'
chk "docker: memory limit support"        '! docker info 2>&1 | grep -qi "No memory limit support"'
chk "docker: cgroup v2"                   'docker info 2>/dev/null | grep -qi "Cgroup Version: 2"'
chk "image $IMAGE present"                'docker image inspect "$IMAGE" >/dev/null 2>&1'
chk "governors performance+powersave"     'grep -q performance /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors && grep -q powersave /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors'
chk "get_throttled = 0x0"                 '[ "$(vcgencmd get_throttled)" = "throttled=0x0" ]'
chk "temperature < 60 C"                  '[ $(cat /sys/class/thermal/thermal_zone0/temp) -lt 60000 ]'
chk "no other container running"          '[ -z "$(docker ps -q)" ]'
chk "ethernet up (not wifi)"              'ip -o link show | grep -q "eth0.*state UP"'
echo "freq min/max (kHz): $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq) / $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq)"
echo "image id: $(docker image inspect --format '{{.Id}}' "$IMAGE" 2>/dev/null)"
[ $ok = 1 ] && echo "ALL OK" || echo "SOME CHECKS FAILED, fix them before continuing"
