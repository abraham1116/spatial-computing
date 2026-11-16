# A tiny remote desktop: a virtual X display, one application, a VNC server and noVNC (the browser client).
# Only the noVNC port is published, bound to 127.0.0.1 by the launcher. Runs as an unprivileged user.
FROM alpine:3.20
RUN apk add --no-cache xvfb x11vnc novnc websockify openbox xterm xclock mousepad font-dejavu \
    && adduser -D -u 10001 desk
COPY start.sh /usr/local/bin/start-desktop
RUN chmod 755 /usr/local/bin/start-desktop
USER desk
ENV DISPLAY=:0 HOME=/home/desk
EXPOSE 6080
ENTRYPOINT ["/usr/local/bin/start-desktop"]
