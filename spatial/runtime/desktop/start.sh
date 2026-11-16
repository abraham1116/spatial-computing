#!/bin/sh
# usage: start.sh <application> [args...]   env: VNC_PASSWORD (required), RESOLUTION (default 1024x640x24)
set -e
[ -n "$VNC_PASSWORD" ] || { echo "VNC_PASSWORD is required" >&2; exit 2; }
Xvfb :0 -screen 0 "${RESOLUTION:-1024x640x24}" -nolisten tcp &
for i in $(seq 1 50); do [ -e /tmp/.X11-unix/X0 ] && break; sleep 0.1; done
openbox >/dev/null 2>&1 &
mkdir -p "$HOME/.vnc"; x11vnc -storepasswd "$VNC_PASSWORD" "$HOME/.vnc/passwd" >/dev/null
x11vnc -display :0 -rfbauth "$HOME/.vnc/passwd" -localhost -forever -shared -quiet -rfbport 5900 &
"$@" &
exec websockify --web /usr/share/novnc 6080 localhost:5900
