#!/bin/sh
# usage: start.sh <application> [args...]
# env: VNC_PASSWORD (required), VIEW_PASSWORD (optional: a second password that can look but not touch),
#      CLIPBOARD (1 default, 0 = no clipboard in either direction), RESOLUTION (default 1024x640x24)
set -e
[ -n "$VNC_PASSWORD" ] || { echo "VNC_PASSWORD is required" >&2; exit 2; }
Xvfb :0 -screen 0 "${RESOLUTION:-1024x640x24}" -nolisten tcp &
for i in $(seq 1 50); do [ -e /tmp/.X11-unix/X0 ] && break; sleep 0.1; done
openbox >/dev/null 2>&1 &
mkdir -p "$HOME/.vnc"
{ echo "$VNC_PASSWORD"; if [ -n "$VIEW_PASSWORD" ]; then echo "__BEGIN_VIEWONLY__"; echo "$VIEW_PASSWORD"; fi; } > "$HOME/.vnc/passwd"
chmod 600 "$HOME/.vnc/passwd"
CLIP=""; [ "${CLIPBOARD:-1}" = "0" ] && CLIP="-noclipboard -nosetclipboard"
x11vnc -display :0 -passwdfile "$HOME/.vnc/passwd" -localhost -forever -shared -quiet -rfbport 5900 $CLIP &
"$@" &
exec websockify --web /usr/share/novnc 6080 localhost:5900
