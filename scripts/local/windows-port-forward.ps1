#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Forward WSL2 ports to the Windows host LAN interface for ii-agent.

.DESCRIPTION
    WSL2 uses NAT, so other LAN devices cannot reach WSL ports directly.
    This script adds netsh portproxy rules and Windows Firewall rules so that:
      - http://<windows-lan-ip>:1420  → ii-agent frontend
      - http://<windows-lan-ip>:8000  → ii-agent backend API / Socket.IO
      - http://<windows-lan-ip>:30000-39999 → sandbox services (noVNC, code-server,
                                               MCP, Vite, dev servers, A2A adapter)
        (Range MUST match SANDBOX_PORT_RANGE_END in docker/docker-compose.local.yaml.)

    Run this script after every WSL2 restart because WSL2 gets a new internal IP
    on each boot. Use -Reset to remove all rules instead.

.PARAMETER Reset
    Remove all portproxy rules and firewall rules created by this script.

.EXAMPLE
    # Forward ports (run after each WSL2 restart)
    .\windows-port-forward.ps1

.EXAMPLE
    # Remove all rules
    .\windows-port-forward.ps1 -Reset
#>

param(
    [switch]$Reset
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Port definitions ──────────────────────────────────────────────────────────

$corePorts = @(
    @{ Port = 1420; Name = "ii-agent Frontend" },
    @{ Port = 8000; Name = "ii-agent Backend" }
)

# Sandbox port range — MUST stay aligned with SANDBOX_PORT_RANGE_START/_END in
# docker/docker-compose.local.yaml. Backend allocates dynamic host ports across
# this whole range (default 30000-39999); any port allocated outside the
# Windows portproxy window is unreachable from the LAN even though it listens
# on 0.0.0.0 inside WSL2 (root cause of broken noVNC / preview links).
$sandboxRangeStart = 30000
$sandboxRangeEnd   = 39999
$sandboxFwRuleName = "ii-agent Sandbox Pool (30000-39999)"

# ── Reset mode ────────────────────────────────────────────────────────────────

if ($Reset) {
    Write-Host "Removing ii-agent portproxy rules..." -ForegroundColor Yellow

    foreach ($entry in $corePorts) {
        netsh interface portproxy delete v4tov4 `
            listenport=$($entry.Port) listenaddress=0.0.0.0 2>$null
        Write-Host "  Removed :$($entry.Port)"
    }

    $regPath = "HKLM:\SYSTEM\CurrentControlSet\Services\PortProxy\v4tov4\tcp"
    if (Test-Path $regPath) {
        for ($p = $sandboxRangeStart; $p -le $sandboxRangeEnd; $p++) {
            Remove-ItemProperty -Path $regPath -Name "0.0.0.0/$p" -ErrorAction SilentlyContinue
        }
        Restart-Service iphlpsvc -Force
    }
    Write-Host "  Removed sandbox range $sandboxRangeStart-$sandboxRangeEnd"

    Write-Host "Removing firewall rules..." -ForegroundColor Yellow
    foreach ($entry in $corePorts) {
        Remove-NetFirewallRule -DisplayName $entry.Name -ErrorAction SilentlyContinue
        Write-Host "  Removed firewall rule: $($entry.Name)"
    }
    Remove-NetFirewallRule -DisplayName $sandboxFwRuleName -ErrorAction SilentlyContinue
    Write-Host "  Removed firewall rule: $sandboxFwRuleName"

    Write-Host "Done. All ii-agent port rules removed." -ForegroundColor Green
    exit 0
}

# ── Get WSL IP ────────────────────────────────────────────────────────────────

Write-Host "Detecting WSL2 IP address..." -ForegroundColor Cyan

# wsl.exe occasionally emits harmless stderr noise during startup
# (e.g. "Failed to mount Z:\\" from a stale DrvFs entry). PowerShell's
# default Stop-on-error behaviour for native commands turns that into a
# script-killing error. We isolate the call inside a try/finally with
# ErrorActionPreference relaxed and merge all streams to $null, then
# parse the captured stdout from a temp file.
$savedEAP = $ErrorActionPreference
$ErrorActionPreference = 'SilentlyContinue'
$wslOutFile = Join-Path $env:TEMP "ii-agent-wsl-ip.$PID.txt"
try {
    # `cmd /c` swallows wsl.exe stderr completely; redirect stdout to file.
    cmd.exe /c "wsl -d Ubuntu-22.04 -- hostname -I 2>nul > `"$wslOutFile`"" 2>$null | Out-Null
    if (-not (Test-Path $wslOutFile) -or (Get-Item $wslOutFile).Length -eq 0) {
        # Fallback: default distro.
        cmd.exe /c "wsl -- hostname -I 2>nul > `"$wslOutFile`"" 2>$null | Out-Null
    }
    $wslHostnameOutput = if (Test-Path $wslOutFile) { Get-Content $wslOutFile -Raw } else { "" }
} finally {
    Remove-Item $wslOutFile -ErrorAction SilentlyContinue
    $ErrorActionPreference = $savedEAP
}

$wslIp = $null
if ($wslHostnameOutput) {
    $tokens = $wslHostnameOutput.Trim().Split() | Where-Object { $_ -match '^\d{1,3}(\.\d{1,3}){3}$' }
    if ($tokens) { $wslIp = $tokens[0] }
}

if (-not $wslIp) {
    Write-Error "Could not detect WSL2 IP. Try `wsl hostname -I` manually in a regular shell."
    exit 1
}

Write-Host "  WSL2 IP: $wslIp" -ForegroundColor Cyan

# ── Core ports ────────────────────────────────────────────────────────────────

Write-Host "`nAdding core port rules..." -ForegroundColor Yellow
foreach ($entry in $corePorts) {
    netsh interface portproxy add v4tov4 `
        listenport=$($entry.Port) listenaddress=0.0.0.0 `
        connectport=$($entry.Port) connectaddress=$wslIp | Out-Null
    Write-Host "  0.0.0.0:$($entry.Port) -> $wslIp`:$($entry.Port)  ($($entry.Name))"
}

# ── Sandbox port range via registry (fast — avoids thousands of netsh calls) ──

Write-Host "`nAdding sandbox port range $sandboxRangeStart-$sandboxRangeEnd via registry..." -ForegroundColor Yellow
Write-Host "  (This forwards the pool allocated dynamically per sandbox container)"
$regPath = "HKLM:\SYSTEM\CurrentControlSet\Services\PortProxy\v4tov4\tcp"
if (-not (Test-Path $regPath)) { New-Item -Path $regPath -Force | Out-Null }
$count = 0
for ($p = $sandboxRangeStart; $p -le $sandboxRangeEnd; $p++) {
    Set-ItemProperty -Path $regPath -Name "0.0.0.0/$p" -Value "$wslIp/$p" -Type String
    $count++
}
# Restart IP Helper service to activate the new registry entries
Restart-Service iphlpsvc -Force
Write-Host "  Added $count entries to registry + restarted IP Helper."

# ── Firewall rules ────────────────────────────────────────────────────────────

Write-Host "`nAdding Windows Firewall inbound rules..." -ForegroundColor Yellow
foreach ($entry in $corePorts) {
    New-NetFirewallRule `
        -DisplayName $entry.Name `
        -Direction Inbound -Protocol TCP `
        -LocalPort $entry.Port `
        -Action Allow `
        -ErrorAction SilentlyContinue | Out-Null
    Write-Host "  Firewall: allow TCP $($entry.Port)  ($($entry.Name))"
}

New-NetFirewallRule `
    -DisplayName $sandboxFwRuleName `
    -Direction Inbound -Protocol TCP `
    -LocalPort "$sandboxRangeStart-$sandboxRangeEnd" `
    -Action Allow `
    -ErrorAction SilentlyContinue | Out-Null
Write-Host "  Firewall: allow TCP $sandboxRangeStart-$sandboxRangeEnd  ($sandboxFwRuleName)"

# ── Summary ───────────────────────────────────────────────────────────────────

Write-Host "`nActive portproxy rules:" -ForegroundColor Cyan
netsh interface portproxy show all

$winIps = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' } |
    Select-Object -ExpandProperty IPAddress)

Write-Host "`nDone. ii-agent should now be reachable at:" -ForegroundColor Green
foreach ($ip in $winIps) {
    Write-Host "  Frontend : http://${ip}:1420"
    Write-Host "  Backend  : http://${ip}:8000"
}
Write-Host "`nRemember: re-run this script after each WSL2 restart (WSL2 IP changes on reboot)."
