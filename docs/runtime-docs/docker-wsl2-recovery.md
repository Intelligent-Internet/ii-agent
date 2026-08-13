# Docker on WSL2 — Failure Diagnosis & Safe Recovery

## Auto-start via systemd (W82 cutover)

As of W82 the ii-agent local stack is owned by a systemd unit on this host:

```
/etc/systemd/system/ii-agent-local.service
# Source-of-truth copy in repo:
docker/systemd/ii-agent-local.service
```

The unit wraps `scripts/stack_control.sh start|stop` as a `Type=oneshot
RemainAfterExit=yes` service, runs as `User=mdear` with `Group=docker`,
declares `Requires=docker.service After=docker.service network-online.target`,
and honors `/tmp/.ii-agent-rebuild-lock` via `ConditionPathExists=!`.

Why this matters: prior to W82 the stack was launched from `~/.bashrc`
with an inline bash block. That pattern:

* Hid container failures from `systemctl status` and `journalctl -u`.
* Raced with login shells on every new terminal.
* Did not auto-restart after a WSL2 guest reboot or a Windows host reboot
  unless the operator opened a terminal first.

### Operator commands

```bash
# Status
systemctl status ii-agent-local.service
docker compose --project-name ii-agent-local ps

# Stop / start / restart
sudo systemctl stop ii-agent-local.service
sudo systemctl start ii-agent-local.service
sudo systemctl restart ii-agent-local.service

# Logs (the unit-level journal — for compose plumbing)
journalctl -u ii-agent-local.service -f

# Logs (per-container — for app behaviour)
docker compose --project-name ii-agent-local logs -f backend
```

### Rebuild workflow (preserves systemd ownership)

The unit honors a lock file so an operator-initiated rebuild is never
clobbered by a stray `systemctl daemon-reload` or a reboot:

```bash
touch /tmp/.ii-agent-rebuild-lock
sudo systemctl stop ii-agent-local.service
scripts/stack_control.sh rebuild   # or build / patch-sandbox / etc.
rm /tmp/.ii-agent-rebuild-lock
sudo systemctl start ii-agent-local.service
```

While the lock exists, `systemctl start ii-agent-local.service` is a
no-op (treated as success, see `ConditionPathExists=`). Forgetting to
remove the lock means the stack will not auto-start on the next reboot;
`systemctl status` will show `condition failed` if you check.

### Reinstall the unit from the repo

```bash
sudo cp docker/systemd/ii-agent-local.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ii-agent-local.service
```

---


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

- `/etc/docker/daemon.json` pins the host explicitly **and** the embedded-DNS
  upstream resolvers (see [Container DNS resolution](#container-dns-resolution)):

  ```json
  {
    "hosts": ["unix:///var/run/docker.sock"],
    "dns": ["1.1.1.1", "8.8.8.8", "1.0.0.1"]
  }
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

---

## Container DNS resolution

### Symptom

Outbound API calls from inside a stack container (Anthropic, OpenAI, web
fetches) fail with `httpx.ConnectError` / `curl (6) Could not resolve host`,
after 4 retries the run is marked `failed`. The A2A inner-loop stream may
still work because it goes container-to-container over the Docker bridge,
but anything that needs public DNS dies.

Backend logs look like:

```
ERROR | ii_agent.agents.models.anthropic.claude:ainvoke_stream | Connection error while calling Claude API: Connection error.
ERROR | ii_agent.agents.models.base:_ainvoke_stream_with_retry  | Model provider error after 4 attempts: Connection error.
```

### Root cause

Docker's embedded resolver inside each container is `127.0.0.11`. That
resolver forwards to the upstream nameservers that `dockerd` captured at
**daemon start time**. On WSL2 the daemon often captures the WSL host's
internal gateway (e.g. `172.29.192.1`) instead of the real public resolvers
from `/etc/resolv.conf`. The host gateway does not run a DNS server, so
every lookup times out.

Confirm with:

```bash
# Inside any stack container — look at "ExtServers:" line
docker exec ii-agent-local-backend-1 cat /etc/resolv.conf

# Bad case (host-gateway upstream, will fail):
#   ExtServers: [host(172.29.192.1)]
# Good case (public resolvers, will work):
#   ExtServers: [1.1.1.1 8.8.8.8 1.0.0.1]
```

Cross-check that the host itself can resolve fine:

```bash
cat /etc/resolv.conf            # host should already point at 1.1.1.1 etc.
getent hosts api.anthropic.com  # must succeed
```

### Fix

Pin the upstream resolvers explicitly in `/etc/docker/daemon.json` so
WSL networking churn cannot poison the capture:

```bash
sudo cp /etc/docker/daemon.json /etc/docker/daemon.json.bak.$(date +%s)
sudo tee /etc/docker/daemon.json > /dev/null <<'EOF'
{
  "hosts": ["unix:///var/run/docker.sock"],
  "dns": ["1.1.1.1", "8.8.8.8", "1.0.0.1"]
}
EOF
sudo systemctl restart docker
```

The restart will bounce every container, but compose services have
`restart: unless-stopped` and rejoin automatically (30–90 s — see
[TL;DR — Recovery decision tree](#tldr--recovery-decision-tree)).

> Note: this is one of the few daemon-config changes that legitimately
> requires a restart. `dockerd` does **not** re-read `dns` settings via
> SIGHUP — only `hosts`, log level, and a few others.

### Verification

```bash
docker exec ii-agent-local-backend-1 sh -c '
  cat /etc/resolv.conf
  getent hosts api.anthropic.com
  curl -sS -o /dev/null -w "HTTP %{http_code} dns=%{time_namelookup}s connect=%{time_connect}s\n" \
       --max-time 10 https://api.anthropic.com/
'
```

Expected: `ExtServers: [1.1.1.1 8.8.8.8 1.0.0.1]`, the hostname resolves,
and `curl` returns `HTTP 404` (404 is correct for a GET on the API root;
the point is that TLS connected).

### Why this keeps happening

The same failure has been observed multiple times on this host. It tends to
appear after one of:

- Cold Windows boot or `wsl --shutdown` followed by a fresh stack start
  before WSL networking has fully converged.
- WSL2 vEthernet adapter renumbering after a Windows update.
- `dockerd` restart while the host's `/etc/resolv.conf` was being rewritten
  by `wsl.conf` `generateResolvConf` / `wsl-vpnkit` / a corporate VPN client.

Keeping the explicit `dns` list in `daemon.json` is the durable fix —
do not remove it even if the symptom seems to have gone away.
