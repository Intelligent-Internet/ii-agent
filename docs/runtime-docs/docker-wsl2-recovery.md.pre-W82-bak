# Docker on WSL2 — Failure Diagnosis & Safe Recovery

This document covers how to diagnose and recover from apparent Docker daemon
failures on this WSL2 host **without** destroying a healthy daemon.

If you remember nothing else: **never `rm` `/var/run/docker.sock` while
`dockerd` is running.** That single act is what produced every "Cannot connect
to the Docker daemon" outage we have investigated on this box.

---

## TL;DR — Recovery decision tree

`docker ps` returns `Cannot connect to the Docker daemon at unix:///var/run/docker.sock`?

1. **Check whether `dockerd` is alive first.**

   ```bash
   pgrep -af dockerd
   ```

   - **Process exists** → daemon is up; the socket or client is the problem.
     Go to step 2. **Do not restart, do not delete the socket.**
   - **No process** → daemon is genuinely down. Skip to step 4.

2. **Check whether the socket is bound to that PID.**

   ```bash
   sudo ss -lxp | grep docker.sock
   ```

   You should see one entry per `/var/run/docker.sock` and `/run/docker.sock`,
   both pointing at the live `dockerd` PID. If the file exists but `ss` shows
   no listener for it (or shows a different PID than the live `dockerd`), the
   socket inode has been orphaned. This is the symptom we have hit; the cause
   is always something that ran `rm /var/run/docker.sock` while the daemon was
   running.

3. **Recover from an orphaned socket.** A clean systemd restart re-binds the
   socket to a fresh daemon and tears down stale state:

   ```bash
   sudo systemctl restart docker
   ```

   Containers with `restart: unless-stopped` (which is what
   `docker-compose.local.yaml` uses) will come back automatically. The restart
   can take 30–90 seconds because each running container is given a graceful
   shutdown window.

4. **Daemon genuinely down.** Start it the supported way:

   ```bash
   sudo systemctl start docker
   sudo systemctl status docker --no-pager
   ```

   Then run the project's start script:

   ```bash
   ./scripts/stack_control.sh start
   ```

---

## What you must never do

| Anti-pattern | Why it breaks things |
|---|---|
| `sudo rm -f /var/run/docker.sock` while `dockerd` is alive | The running daemon keeps a listening fd on the now-unlinked inode. The on-disk path either disappears or gets recreated by another process; either way every client gets `Cannot connect to the Docker daemon`. The daemon itself looks fine in `ps` and `systemctl status`. |
| `sudo dockerd ... &` from a shell script | systemd doesn't track it, can't restart it, can't stop it cleanly. Running it alongside the systemd-managed daemon produces split-brain (two PIDs, one socket inode), which is exactly the failure mode we hit. |
| Treating one transient `docker info` failure as "daemon dead" | `docker info` can fail momentarily during WSL2 vmmem warm-up, after a Windows host suspend/resume, or while a slow operation holds the daemon. Retry before doing anything destructive. |
| `docker ps -a` followed by mass `docker rm` to "clean up" | The compose stack's named containers are the source of truth — let `stack_control.sh` manage them. |

---

## How `dockerd` runs on this box (WSL2 specifics)

WSL2 has historically had broken systemd integration. On this host:

- `/etc/wsl.conf` enables systemd, but systemd is not always PID 1 in the
  classic sense; some unit interactions are flaky.
- The Docker service drop-in at
  `/etc/systemd/system/docker.service.d/override.conf` overrides `ExecStart`
  to drop `-H fd://` (socket activation), because socket activation requires
  a fully functioning systemd. Effective command line:

  ```
  /usr/bin/dockerd --containerd=/run/containerd/containerd.sock
  ```

- `/etc/docker/daemon.json` pins the host explicitly:

  ```json
  { "hosts": ["unix:///var/run/docker.sock"] }
  ```

- Restart-on-crash: the upstream `docker.service` ships with `Restart=always`
  and `RestartSec=2s`. systemd **will** restart `dockerd` automatically if it
  crashes. The cases we have seen called "Docker is down" were not crashes —
  they were the running daemon's socket being deleted by a recovery hook.

If you ever want to harden the restart behaviour further, append to the same
drop-in:

```ini
[Service]
Restart=always
RestartSec=5s
StartLimitBurst=5
StartLimitIntervalSec=60
```

then `sudo systemctl daemon-reload`.

---

## Auto-recovery hook in `~/.bashrc`

The bashrc snippet that auto-starts the ii-agent stack on shell open follows
these rules:

1. If `docker info` works, do nothing.
2. If `docker info` fails **but `pgrep -x dockerd` succeeds**, the daemon is
   alive — wait up to 15 s for it to become responsive. Never touch the socket.
3. Only if `pgrep -x dockerd` fails do we call
   `sudo systemctl start docker` and wait up to 30 s.

The previous version of this hook ran `sudo rm -f /var/run/docker.sock` and
forked a bare `sudo dockerd ... &`. That is what produced the orphaned-socket
outages. Do not reintroduce it.

---

## Diagnostic snippets

Single-command health snapshot:

```bash
echo "=== dockerd ===";     pgrep -af dockerd
echo "=== systemd unit =="; systemctl is-active docker; systemctl is-enabled docker
echo "=== socket fd ===";   sudo ss -lxp | grep docker.sock
echo "=== socket file ==="; ls -la /var/run/docker.sock /run/docker.sock
echo "=== ping ===";        timeout 3 docker info > /dev/null 2>&1 && echo OK || echo FAIL
```

Recent daemon log (last 50 events, no DEBUG noise):

```bash
sudo journalctl -u docker --since "1 hour ago" --no-pager \
  | grep -vE 'level=debug' | tail -50
```

Confirm containers will come back after a restart:

```bash
docker inspect --format '{{.Name}} {{.HostConfig.RestartPolicy.Name}}' \
  $(docker ps -aq) | sort
```

For the ii-agent stack everything should report `unless-stopped`.

---

## Stack-level recovery (after Docker is healthy again)

Use the project script — never raw `docker compose`:

```bash
./scripts/stack_control.sh status            # what's up?
./scripts/stack_control.sh start             # bring stack up
./scripts/stack_control.sh restart           # full restart
./scripts/stack_control.sh logs backend -f   # follow backend logs
```

If a single service is wedged after Docker recovers but the rest are fine,
prefer a targeted restart over restarting the whole stack:

```bash
./scripts/stack_control.sh rebuild backend   # rebuild + restart one service
```
