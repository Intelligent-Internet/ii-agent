# II-Agent WSL2 Power Recovery

## Purpose

Recover ii-agent after an unplanned Windows host power cycle, including before user logon. The repository is the source of truth for the Windows scripts; installation copies the monitor to `C:\ProgramData\ii-agent\ii-agent-recovery-monitor.ps1` so the scheduled task can start WSL without first accessing an unavailable WSL share.

## Components

| Component | Repository location or name | Responsibility |
| --- | --- | --- |
| Windows task | `ii-agent WSL2 Port Forward` | One task with startup and logon triggers (`IgnoreNew`), running an elevated Windows-local copy of the monitor. |
| Recovery monitor | [`scripts/local/windows/ii-agent-recovery-monitor.ps1`](../../scripts/local/windows/ii-agent-recovery-monitor.ps1) | Starts WSL, retries Linux service startup, refreshes Windows forwarding, and waits for application readiness. |
| Installer | [`scripts/local/windows/install-ii-agent-recovery-monitor.ps1`](../../scripts/local/windows/install-ii-agent-recovery-monitor.ps1) | Deploys the monitor to Windows and registers the task. |
| WSL service | [`docker/systemd/ii-agent-local.service`](../../docker/systemd/ii-agent-local.service) | Starts the compose stack after `docker.service`. |

The WSL `/etc/wsl.conf` boot command requests the same task when WSL starts for other reasons. `IgnoreNew` prevents simultaneous copies of that task. A logon-only install does **not** provide unattended recovery before user logon.

## Access From Windows

From an **Administrator PowerShell** window, start the distribution before accessing its UNC share. Do not run the installer if the share is unavailable:

```powershell
wsl.exe -d Ubuntu-22.04 -- true
$repoRoot = "\\wsl.localhost\Ubuntu-22.04\home\mdear\workspaces\git\ii-agent"
$installer = Join-Path $repoRoot 'scripts\local\windows\install-ii-agent-recovery-monitor.ps1'
if (-not (Test-Path -LiteralPath $installer)) { throw "WSL share unavailable: $installer" }
```

For an optional PowerShell drive in the **current interactive session** (choose any unused name):

```powershell
New-PSDrive -Name IIAGENT -PSProvider FileSystem -Root $repoRoot
Set-Location IIAGENT:\scripts\local\windows
```

The installer uses the UNC source only after this check; scheduled tasks use the deployed Windows-local copy, never this session's mapped drive or the UNC path.

## Recovery Contract

The monitor starts WSL and waits up to 90 minutes. It:

1. Obtains the WSL2 IPv4 address with a bounded WSL command; a stale `Z:` DrvFs mount warning is non-fatal when the command succeeds.
2. Waits for systemd to finish starting (`running` or `degraded`) and for Docker and the II-Agent unit to be active. `degraded` can reflect unrelated units such as SEATS backups; II-Agent's own units must still be active. Only after boot completes, if either unit is inactive or failed, it retries `systemctl start` every two minutes while honoring the rebuild lock. It never restarts a unit or starts one while either is transitioning.
3. Requires `scripts/stack_control.sh status --ready --timeout 0` to pass on each Windows poll: all five core Compose services must be running, their healthchecked services healthy, the backend and frontend reachable, and the enabled sandbox pool available. The monitor owns the 90-minute retry budget; a manual `status --ready` instead polls for up to 90 minutes. It also probes frontend HTTP `200` and backend `GET /health/ready` HTTP `200` at the WSL address. Three consecutive healthy polls at the same WSL IP are required.
4. Only then ensures firewall rules for frontend `1420`, backend `8000`, and sandbox ports `30000-39999`; it updates changed port-proxy registry entries and refreshes IP Helper only when necessary. Check LAN reachability separately from another machine after reboot.

`/health/ready` requires both PostgreSQL and Redis. The monitor cannot repair Windows/WSL storage corruption or a permanently failing Docker daemon; it logs retries and eventually exits nonzero.

The task is configured to start and continue while the UPS is on battery power. Its 100-minute execution limit exceeds the monitor's 90-minute readiness budget. Runtime logs are written to `C:\ProgramData\ii-agent\logs\ii-agent-recovery-monitor.log`, not into the tracked source tree.

## Install Or Update

First check `/etc/wsl.conf` with `wsl.exe -d Ubuntu-22.04 -u root -- cat /etc/wsl.conf`. The single `[boot]` section must include the lines below. If missing, edit it with `wsl.exe -d Ubuntu-22.04 -u root -- nano /etc/wsl.conf`. Do not add a second `[boot]` section. If you changed it, close WSL sessions at a maintenance window and run `wsl.exe --shutdown` from Windows to apply it, then restart the distro with `wsl.exe -d Ubuntu-22.04 -- true`.

```ini
[boot]
systemd=true
command=/mnt/c/Windows/System32/schtasks.exe /Run /TN "ii-agent WSL2 Port Forward" >/dev/null 2>&1 || true
```

In Administrator PowerShell, install the Linux unit and enable it alongside Docker. The source path below assumes this repository is at the location shown above:

```powershell
wsl.exe -d Ubuntu-22.04 -- true
$repoRoot = "\\wsl.localhost\Ubuntu-22.04\home\mdear\workspaces\git\ii-agent"
wsl.exe -d Ubuntu-22.04 -u root -- install -m 644 /home/mdear/workspaces/git/ii-agent/docker/systemd/ii-agent-local.service /etc/systemd/system/ii-agent-local.service
if ($LASTEXITCODE -ne 0) { throw 'Could not install the Linux II-Agent unit.' }
wsl.exe -d Ubuntu-22.04 -u root -- systemctl daemon-reload
if ($LASTEXITCODE -ne 0) { throw 'Could not reload Linux systemd.' }
wsl.exe -d Ubuntu-22.04 -u root -- systemctl enable docker.service ii-agent-local.service
if ($LASTEXITCODE -ne 0) { throw 'Linux Docker or II-Agent unit enablement failed.' }
wsl.exe -d Ubuntu-22.04 -u root -- timeout 120 systemctl start docker.service ii-agent-local.service
if ($LASTEXITCODE -ne 0) { Write-Warning 'Initial Linux start failed or timed out; install the Windows recovery task below to retry it.' }
wsl.exe -d Ubuntu-22.04 -u root -- systemctl is-enabled docker.service ii-agent-local.service
```

Then install recovery. IP Helper must be running to activate Windows port forwarding; an older monitor may have left it stopped. The child PowerShell uses `Bypass` because unsigned scripts on the WSL share may be blocked by `AllSigned`. For recovery **at logon**, no Windows account password is needed:

```powershell
$repoRoot = "\\wsl.localhost\Ubuntu-22.04\home\mdear\workspaces\git\ii-agent"
$installer = Join-Path $repoRoot 'scripts\local\windows\install-ii-agent-recovery-monitor.ps1'
if (-not (Test-Path -LiteralPath $installer)) { throw "WSL share unavailable: $installer" }
if ((Get-Service iphlpsvc).Status -ne 'Running') { Start-Service iphlpsvc -ErrorAction Stop }
if ((Get-Service iphlpsvc).Status -ne 'Running') { throw 'IP Helper did not start.' }
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer
if ($LASTEXITCODE -ne 0) { throw 'Recovery task installation failed.' }
```

If installation fails before task registration, the old task registration remains unchanged, but the deployed monitor may have been updated. After correcting the error, rerun this command block and confirm the Windows-local action, source/deployed hashes, and both triggers in **Verify** before relying on startup recovery.

For **unattended recovery before logon**, run the same installer with `-InstallStartupTask` instead. It prompts locally for the Windows account **password**, not the Windows Hello PIN. Task Scheduler retains the credential; do not paste it into a command or this repository. If the password is unknown, the logon-only task can run but pre-logon recovery is **not configured**. Recover or reset the account password using Windows account recovery before installing the startup trigger; do not substitute a `SYSTEM` task, which cannot be assumed to see this user's WSL distribution. A startup trigger alone does not prove the task works before logon: test it after an actual reboot.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer -InstallStartupTask
if ($LASTEXITCODE -ne 0) { throw 'Unattended recovery task installation failed.' }
```

Without `-InstallStartupTask`, only the logon trigger is installed. If an existing task has a startup trigger, the installer refuses to downgrade it without this flag. If an old monitor is still running, the installer will not interrupt it. To exercise the newly installed action now, use Administrator PowerShell to stop that old instance, confirm it stopped, and start the task:

```powershell
Stop-ScheduledTask -TaskName 'ii-agent WSL2 Port Forward'
if ((Get-ScheduledTask -TaskName 'ii-agent WSL2 Port Forward').State -eq 'Running') { throw 'Old monitor is still running.' }
Start-ScheduledTask -TaskName 'ii-agent WSL2 Port Forward'
```

Task registration alone is not proof of successful recovery. Do not stop a healthy in-progress monitor unless you intend to replace it.

## Verify

```powershell
$task = Get-ScheduledTask -TaskName 'ii-agent WSL2 Port Forward'
$task.Actions | Format-List Execute, Arguments
$task.Triggers | Select-Object @{Name='Type';Expression={$_.CimClass.CimClassName}}, Enabled
Get-ScheduledTaskInfo -TaskName $task.TaskName | Format-List LastRunTime, LastTaskResult
$repoMonitor = Join-Path $repoRoot 'scripts\local\windows\ii-agent-recovery-monitor.ps1'
$localMonitor = Join-Path $env:ProgramData 'ii-agent\ii-agent-recovery-monitor.ps1'
Get-FileHash $repoMonitor, $localMonitor | Select-Object Path, Hash
Get-Content 'C:\ProgramData\ii-agent\logs\ii-agent-recovery-monitor.log' -Tail 50
curl.exe -I http://192.168.2.2:1420/
curl.exe http://192.168.2.2:8000/health/ready
```

Expect a Windows-local `-File` path in the task action, matching hashes for source/deployed monitor, a `ready` log entry, and `LastTaskResult` of `0` after the task finishes. **Both** `MSFT_TaskBootTrigger` and `MSFT_TaskLogonTrigger` must be present for unattended recovery; logon-only setup has just the logon trigger. `267009` means the task is still running, not success. The frontend must return HTTP `200`; readiness JSON must show database and Redis `ok`. Check `netsh interface portproxy show v4tov4` and Windows firewall rules for 1420, 8000, and 30000-39999 as well.

For an end-to-end unattended test, schedule an appropriate maintenance window, reboot Windows, and **before logging in** verify the two endpoints from another LAN machine. A successful manual run or logon-triggered run does not prove pre-logon recovery. Never delete earlier Windows-local scripts until the new task has exited `0` and no other task references them.

## Diagnose Slow Recovery

The monitor does not make Docker boot faster; it makes delayed boot non-interactive. On 2026-09-26, WSL2 took about 8 minutes to reach the userspace target, with `containerd.service` becoming available after almost 6 minutes. Use the WSL commands below when recovery exceeds the monitor budget:

```bash
systemd-analyze critical-chain docker.service ii-agent-local.service --no-pager
systemctl status docker.service ii-agent-local.service --no-pager
journalctl -b -u docker.service -u ii-agent-local.service --no-pager
```

## Disable Or Remove

Disable both startup and logon recovery:

```powershell
Disable-ScheduledTask -TaskName 'ii-agent WSL2 Port Forward'
```

Remove the task entirely:

```powershell
Unregister-ScheduledTask -TaskName 'ii-agent WSL2 Port Forward' -Confirm:$false
```