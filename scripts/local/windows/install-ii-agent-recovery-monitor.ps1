#Requires -RunAsAdministrator

[CmdletBinding()]
param(
    [switch]$InstallStartupTask
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$monitorPath = Join-Path $PSScriptRoot "ii-agent-recovery-monitor.ps1"
if (-not (Test-Path -LiteralPath $monitorPath)) {
    throw "WSL share or recovery monitor unavailable: $monitorPath. Start Ubuntu-22.04 and retry."
}

$oldStartupTask = Get-ScheduledTask -TaskName "ii-agent WSL2 Startup Monitor" -ErrorAction SilentlyContinue
if ($null -ne $oldStartupTask -and -not $InstallStartupTask) {
    throw "An older unattended startup task exists; rerun with -InstallStartupTask to retain pre-logon recovery."
}

$existingTask = Get-ScheduledTask -TaskName "ii-agent WSL2 Port Forward" -ErrorAction SilentlyContinue
$hasStartupTrigger = $null -ne $existingTask -and @($existingTask.Triggers | Where-Object {
    $_.CimClass.CimClassName -eq "MSFT_TaskBootTrigger"
}).Count -gt 0
if ($hasStartupTrigger -and -not $InstallStartupTask) {
    throw "This task already has an unattended startup trigger; rerun with -InstallStartupTask to retain it."
}

$installDirectory = Join-Path $env:ProgramData "ii-agent"
New-Item -ItemType Directory -Path $installDirectory -Force | Out-Null
$installedMonitor = Join-Path $installDirectory "ii-agent-recovery-monitor.ps1"
$stagedMonitor = Join-Path $installDirectory "ii-agent-recovery-monitor.ps1.new"
Copy-Item -LiteralPath $monitorPath -Destination $stagedMonitor -Force
Copy-Item -LiteralPath $stagedMonitor -Destination $installedMonitor -Force
Remove-Item -LiteralPath $stagedMonitor -Force

$userName = "{0}\{1}" -f $env:USERDOMAIN, $env:USERNAME
$arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$installedMonitor`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 100) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable
$settings.DisallowStartIfOnBatteries = $false
$settings.StopIfGoingOnBatteries = $false

$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $userName

if ($InstallStartupTask) {
    $credential = Get-Credential -UserName $userName -Message "Enter the Windows account password for unattended ii-agent startup."
    Register-ScheduledTask `
        -TaskName "ii-agent WSL2 Port Forward" `
        -Description "Starts WSL2 and waits for ii-agent readiness after startup or logon." `
        -Action $action `
        -Trigger @((New-ScheduledTaskTrigger -AtStartup), $logonTrigger) `
        -Settings $settings `
        -User $credential.UserName `
        -Password $credential.GetNetworkCredential().Password `
        -RunLevel Highest `
        -Force | Out-Null
} else {
    $principal = New-ScheduledTaskPrincipal -UserId $userName -LogonType Interactive -RunLevel Highest
    Register-ScheduledTask `
        -TaskName "ii-agent WSL2 Port Forward" `
        -Description "Starts WSL2 and waits for ii-agent readiness after logon." `
        -Action $action `
        -Trigger $logonTrigger `
        -Settings $settings `
        -Principal $principal `
        -Force | Out-Null
}

if ($null -ne $oldStartupTask) {
    Unregister-ScheduledTask -TaskName "ii-agent WSL2 Startup Monitor" -Confirm:$false
}

$task = Get-ScheduledTask -TaskName "ii-agent WSL2 Port Forward"
if ($task.State -ne "Running") {
    Start-ScheduledTask -TaskName "ii-agent WSL2 Port Forward"
} else {
    Write-Host "A prior monitor is still running; the new action will run at its next trigger."
}
Write-Host "ii-agent recovery task installed using $installedMonitor. Check the monitor log for readiness."
if ($InstallStartupTask) {
    Write-Host "Unattended Windows startup and user logon triggers installed on the same task."
}