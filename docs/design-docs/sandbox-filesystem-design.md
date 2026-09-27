# Sandbox Filesystem Design

**Date:** 2026-04-25
**Scope:** File layout, ownership model, write paths, and skill deployment in Docker sandboxes
**Status:** Authoritative — implemented and tested

---

## Table of Contents

1. [Container Hardening Summary](#container-hardening-summary)
2. [Filesystem Layout](#filesystem-layout)
3. [User and Privilege Model](#user-and-privilege-model)
4. [Write Path Rules](#write-path-rules)
5. [Skill Deployment Pipeline](#skill-deployment-pipeline)
6. [File Ownership Invariants](#file-ownership-invariants)
7. [Provider Differences (Docker vs E2B)](#provider-differences-docker-vs-e2b)
8. [Historical Bugs and Fixes](#historical-bugs-and-fixes)

---

## Container Hardening Summary

Docker sandboxes are created in `agents/sandboxes/docker.py` with these security constraints:

| Constraint | Value | Purpose |
|---|---|---|
| `read_only=True` | rootfs is read-only | Prevents writes to the container image layer |
| `cap_drop=ALL` | All Linux capabilities dropped | Defence-in-depth |
| `cap_add` | CHOWN, SETUID, SETGID, DAC_OVERRIDE, FOWNER | Minimum needed for package installs / user management |
| `security_opt=["no-new-privileges"]` | Prevents privilege escalation via setuid binaries | |
| `mem_limit=3072m` | 3 GB | Sandbox memory cap |
| `pids_limit=512` | 512 processes | Fork-bomb mitigation |
| Default user | `user` (uid 1001, gid 1001) | Non-root; declared in `e2b.Dockerfile` |

---

## Filesystem Layout

```
/workspace/          ← named Docker volume, rw, uid=1001 (user:user 755)
│                      This is the ONLY path writable by host-mediated upload
│                      (put_archive).  See Write Path Rules below.
│
├── .skills/         ← skill deployment staging area, created on first use
│   ├── agent-browser/   ← extracted skill directory (user:user 755)
│   ├── pdf/
│   └── .agent-browser.zip  ← staging zip, removed after extraction
│
└── (agent work files)

/tmp/                ← tmpfs, 512 MB, writable in-container
/var/tmp/            ← tmpfs, 256 MB, writable in-container
/run/                ← tmpfs, 64 MB, writable in-container
/home/user/          ← tmpfs, 1 GB, uid=1001 gid=1001 exec, writable in-container

(everything else)    ← read-only rootfs, writes fail with EROFS
```

---

## User and Privilege Model

| Identity | UID | GID | Access |
|---|---|---|---|
| `user` (default) | 1001 | 1001 | Owns `/workspace`, `/home/user`. Can read/write all tmpfs paths. Cannot write rootfs. |
| `root` | 0 | 0 | Used only when explicitly requested via `user="root"` in `run_command`. Required for package installs (`apt`), system service management. Never used for skill deployment. |
| Backend process | N/A | N/A | Communicates with the container via `docker exec` (default user) or `put_archive` (files tagged uid=1001). Never requires a root shell for normal agent work. |

**Key constants** (defined once in `agents/sandboxes/docker.py`):

```python
_SANDBOX_USER_UID = 1001
_SANDBOX_USER_GID = 1001
```

These are embedded in every `put_archive` tar entry so the sandbox user can manage uploaded files without CAP_FOWNER.

---

## Write Path Rules

### Rule 1 — Host-mediated uploads (`write_file` / `upload_file` / `put_archive`) must target `/workspace`

Docker's `put_archive` API rejects destinations outside the writable bind-mount when `read_only=True` is set, even when the destination is a tmpfs mount that in-container writes succeed against (moby/moby#42333). The error is:

```
container rootfs is marked read-only
```

**Correct staging path:** `/workspace/.skills/.{skill_name}.zip`  
**Incorrect:** `/tmp/{skill_name}.zip` — will fail with the above error

### Rule 2 — Run commands default to the sandbox user; root is explicit and exceptional

`DockerSandbox.run_command()` accepts an optional `user` keyword that maps directly to Docker's `exec_run(user=...)`. When omitted, the default container user (`user`, uid 1001) is used.

Using `user="root"` to create directories under `/workspace` breaks the ownership invariant: the directory becomes `root:root 755`, so the sandbox user cannot remove files inside it, causing `Permission denied` on cleanup.

**Correct:**
```python
await sandbox.run_command(f"mkdir -p /workspace/.skills")      # runs as uid 1001
await sandbox.write_file("/workspace/.skills/.pdf.zip", data)  # tar entry uid=1001
await sandbox.run_command(f"unzip /workspace/.skills/.pdf.zip -d /workspace/.skills/pdf")
await sandbox.run_command(f"rm -f /workspace/.skills/.pdf.zip")  # user owns it → ok
```

**Incorrect (caused production bug 2026-04-25):**
```python
await sandbox.run_command("mkdir -p /workspace/.skills", user="root")  # root:root!
await sandbox.write_file("...", data)                                    # uid=1001
await sandbox.run_command("rm -f ...", user="root")                     # unnecessary escalation
# When user="root" was accidentally omitted on the rm call:
await sandbox.run_command("rm -f ...")  # uid=1001 → EPERM on root:root dir
```

### Rule 3 — `user="root"` is only appropriate for system-level operations

Acceptable uses of `user="root"` inside the sandbox:
- `apt-get install`, `pip install --user`, `npm install -g` (need root for system dirs)  
- Managing system services (e.g. `service postgresql start`)
- GitHub clone into paths not under `/workspace` (legacy pattern)

Not acceptable:
- Creating or removing files/directories under `/workspace` or `/home/user`
- Any skill deployment step

---

## Skill Deployment Pipeline

Skills are deployed on demand when the agent invokes the `Skill` tool. The canonical implementation is in `agents/skills/storage.py::copy_skill_to_sandbox`.

```
SkillTool.execute("agent-browser")
  └── copy_skill_to_sandbox(storage_uri="builtin:agent-browser", skill_name="agent-browser", sandbox=...)
        1. Resolve storage_uri → local directory (builtin) or download from GCS (custom)
        2. Zip skill directory in-memory → bytes
        3. sandbox.run_command("mkdir -p /workspace/.skills")            # uid=1001
        4. sandbox.write_file("/workspace/.skills/.agent-browser.zip")   # uid=1001 tar entry
        5. sandbox.run_command("mkdir -p /workspace/.skills/agent-browser")
        6. sandbox.run_command("unzip ... /workspace/.skills/agent-browser")
        7. sandbox.run_command("chmod -R 755 /workspace/.skills/agent-browser")
        8. sandbox.run_command("rm -f /workspace/.skills/.agent-browser.zip")  # uid=1001 → ok
        └── returns "/workspace/.skills/agent-browser"
```

**Why zip?** Both Docker (`put_archive` = single tar) and E2B (`files.write` = single file) are optimised for uploading one object. Uploading a skill directory as dozens of small files is slow. A single in-memory zip → single upload → single `unzip` is fast and atomic.

**Why stage under `/workspace`?** See Rule 1. `/tmp` is a tmpfs and is writable in-container, but the Docker daemon's `put_archive` API path rejects it.

### Storage URI Scheme

| Prefix | Resolution | Who owns |
|---|---|---|
| `builtin:{name}` | `src/ii_agent/agents/skills/builtin/{name}/` | Shipped with ii-agent source |
| `users/{uid}/skills/{name}.zip` | GCS object (prod) or MinIO (local) | User-uploaded via GitHub import |
| `/absolute/path` | Local filesystem (legacy, unused in prod) | — |

---

## File Ownership Invariants

These invariants are enforced by construction and must not be violated:

| Path | Owner | Mode | Enforced by |
|---|---|---|---|
| `/workspace` | `user:user` | 755 | Named volume pre-ownership in Dockerfile |
| `/workspace/.skills/` | `user:user` | 755 | `mkdir -p` runs as uid=1001 (default) |
| `/workspace/.skills/{name}/` | `user:user` | 755 | `unzip` + `chmod -R 755` run as uid=1001 |
| Files uploaded via `write_file` | `user:user` | 644 | `_put_file` sets `info.uid=1001, info.gid=1001` |
| `/home/user` | `user:user` | — | tmpfs option `uid=1001,gid=1001` |
| `/tmp`, `/var/tmp`, `/run` | root | 1777 | Standard tmpfs defaults |

**Breaking this table causes `Permission denied` errors** when the sandbox user tries to clean up or overwrite files created by root. All skill deployment code must respect these invariants.

---

## Provider Differences (Docker vs E2B)

| Operation | Docker | E2B |
|---|---|---|
| `write_file(path, data)` | `put_archive` with tar entry uid=1001 → file owned by sandbox user | `sandbox.files.write(path, data)` → owned by E2B's default user |
| `run_command(cmd)` | `docker exec` as default container user (uid=1001) | `sandbox.commands.run(cmd)` as E2B default user |
| `run_command(cmd, user="root")` | `docker exec --user root` | Forwarded as `user="root"` kwarg to E2B SDK; E2B may or may not honour it depending on template |
| Stage uploads under | `/workspace` (required — see Rule 1) | Any writable path (`/tmp` works in E2B) |
| `/tmp` via `put_archive` | **Fails** — container rootfs is marked read-only | Not applicable |

The `Sandbox.run_command` base class now declares `user: Optional[str] = None` explicitly, with documentation that callers must not rely on `user` for security-critical isolation — it is only for file-ownership convenience where the provider is known to support it.

---

## Historical Bugs and Fixes

### 2026-04-25 — Skill activation fails with `Permission denied`

**Symptom:** `Skill` tool returned an error for all users; agent couldn't load `agent-browser` or any other skill.

**Root cause:** `copy_skill_to_sandbox` ran `mkdir -p /workspace/.skills` with `user="root"`, creating the directory owned by `root:root`. When cleanup tried `rm -f .agent-browser.zip` without an explicit `user` argument (i.e. as the default sandbox user, uid=1001), the kernel rejected the unlink because the parent directory was owned by root and had mode 755 (no write for others).

**Fix:** Removed all `user="root"` from skill deployment. `/workspace` is `user:user 755`; the sandbox user can create, write, and remove everything inside it without root escalation.

**Files changed:**
- `agents/skills/storage.py` — removed `user="root"` from all 5 `run_command` calls; dropped the now-unnecessary `chown -R user:user` step; added `-f` to `rm` for idempotency
- `settings/skills/storage.py` — same fix applied to the unused duplicate; dead `copy_skill_to_sandbox`, `skill_exists`, `resolve_storage_uri`, `create_skill_zip_from_dir` functions removed
- `agents/sandboxes/base.py` — added explicit `user: Optional[str] = None` to the abstract `run_command` signature with security documentation
- `agents/sandboxes/e2b.py` — added matching `user` parameter and forwards it to the E2B SDK
