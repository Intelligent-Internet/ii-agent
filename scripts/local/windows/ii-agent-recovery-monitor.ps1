#Requires -RunAsAdministrator

[CmdletBinding()]
param(
    [ValidateRange(60, 5400)]
    [int]$TimeoutSeconds = 5400,

    [ValidateRange(5, 60)]
    [int]$PollIntervalSeconds = 10
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$distribution = "Ubuntu-22.04"
$linuxUser = "mdear"
$wslExe = Join-Path $env:SystemRoot "System32\wsl.exe"
$logDirectory = Join-Path $env:ProgramData "ii-agent\logs"
$logPath = Join-Path $logDirectory "ii-agent-recovery-monitor.log"
$corePorts = @(
    @{ Port = 1420; Name = "ii-agent Frontend" },
    @{ Port = 8000; Name = "ii-agent Backend" }
)
$sandboxRangeStart = 30000
$sandboxRangeEnd = 39999
$sandboxFwRuleName = "ii-agent Sandbox Pool (30000-39999)"
$portProxyRegistryPath = "SYSTEM\CurrentControlSet\Services\PortProxy\v4tov4\tcp"
$portProxyRefreshPending = $false

function Write-Log {
    param([string]$Message)

    if (-not (Test-Path -LiteralPath $logDirectory)) {
        New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    }

    $line = "{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $Message
    Add-Content -LiteralPath $logPath -Value $line -Encoding Ascii
}

function Invoke-WslCommand {
    param(
        [string]$Arguments,
        [int]$TimeoutMilliseconds = 30000
    )

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $wslExe
    $startInfo.Arguments = "-d $distribution $Arguments"
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    try {
        if (-not $process.Start()) {
            throw "Could not start wsl.exe."
        }
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutMilliseconds)) {
            $process.Kill()
            $process.WaitForExit(5000) | Out-Null
            return [PSCustomObject]@{ TimedOut = $true; ExitCode = -1; Output = ""; Error = "" }
        }
        return [PSCustomObject]@{
            TimedOut = $false
            ExitCode = $process.ExitCode
            Output = $stdout.GetAwaiter().GetResult()
            Error = $stderr.GetAwaiter().GetResult()
        }
    } finally {
        $process.Dispose()
    }
}

function Get-WslIpAddress {
    $result = Invoke-WslCommand -Arguments "-u $linuxUser -- hostname -I"
    if ($result.TimedOut -or $result.ExitCode -ne 0) {
        return $null
    }

    $result.Output -split "\s+" |
        Where-Object { $_ -match "^\d{1,3}(\.\d{1,3}){3}$" } |
        Select-Object -First 1
}

function Ensure-IpHelper {
    $deadline = (Get-Date).AddSeconds(30)
    $stopPendingAt = $null
    do {
        $service = Get-CimInstance Win32_Service -Filter "Name='iphlpsvc'"
        if ($service.State -eq "Running") {
            return
        }
        if ($service.State -eq "Stopped") {
            Write-Log "Starting IP Helper."
            Start-Service -Name iphlpsvc
        } elseif ($service.State -eq "Stop Pending" -and $service.ProcessId -gt 0) {
            if ($null -eq $stopPendingAt) {
                $stopPendingAt = Get-Date
            } elseif ((Get-Date) -ge $stopPendingAt.AddSeconds(10)) {
                $hostedServices = @(Get-CimInstance Win32_Service | Where-Object { $_.ProcessId -eq $service.ProcessId })
                if ($hostedServices.Count -ne 1) {
                    throw "IP Helper is stuck stopping in a shared service host; refusing to terminate other services."
                }
                if (Get-Process -Id $service.ProcessId -ErrorAction SilentlyContinue) {
                    Write-Log "IP Helper is stuck stopping; terminating its isolated service host."
                    try {
                        Stop-Process -Id $service.ProcessId -Force -ErrorAction Stop
                    } catch {
                        if (Get-Process -Id $service.ProcessId -ErrorAction SilentlyContinue) {
                            throw
                        }
                    }
                }
            }
        } else {
            $stopPendingAt = $null
        }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)

    throw "IP Helper did not reach Running within 30 seconds."
}

function Restart-IpHelper {
    if ((Get-Service -Name iphlpsvc).Status -eq "Running") {
        & sc.exe stop iphlpsvc | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Could not stop IP Helper (sc.exe exit $LASTEXITCODE)."
        }
    }
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        $service = Get-CimInstance Win32_Service -Filter "Name='iphlpsvc'"
        if ($service.State -eq "Stopped") {
            break
        }
        Start-Sleep -Seconds 1
    }

    Ensure-IpHelper
}

function Ensure-FirewallRule {
    param([string]$Name, [string]$Ports)

    $rule = Get-NetFirewallRule -DisplayName $Name -ErrorAction SilentlyContinue
    if (-not $rule) {
        New-NetFirewallRule -DisplayName $Name -Direction Inbound -Protocol TCP -LocalPort $Ports -Action Allow | Out-Null
    } elseif ($rule.Enabled -ne "True") {
        $rule | Enable-NetFirewallRule
    }
}

function Set-PortProxy {
    param([string]$WslIp)

    foreach ($entry in $corePorts) {
        Ensure-FirewallRule -Name $entry.Name -Ports ([string]$entry.Port)
    }
    Ensure-FirewallRule -Name $sandboxFwRuleName -Ports "$sandboxRangeStart-$sandboxRangeEnd"

    $key = [Microsoft.Win32.Registry]::LocalMachine.CreateSubKey($portProxyRegistryPath)
    if ($null -eq $key) {
        throw "Unable to open Windows port-proxy registry key."
    }
    $changed = $false
    try {
        $ports = @($corePorts | ForEach-Object { $_.Port }) + @($sandboxRangeStart..$sandboxRangeEnd)
        foreach ($port in $ports) {
            $name = "0.0.0.0/$port"
            $value = "$WslIp/$port"
            if ($key.GetValue($name) -ne $value) {
                $key.SetValue($name, $value, [Microsoft.Win32.RegistryValueKind]::String)
                $changed = $true
            }
        }
    } finally {
        $key.Dispose()
    }
    if ($changed) {
        $script:portProxyRefreshPending = $true
        Write-Log "Updated Windows core and sandbox port proxies for $WslIp; restarting IP Helper."
    }
    if ($script:portProxyRefreshPending) {
        Restart-IpHelper
        $script:portProxyRefreshPending = $false
    }
}

function Test-HttpStatus {
    param([string]$Uri)

    try {
        $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 5
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

try {
    Write-Log "Monitor started. Waiting up to $TimeoutSeconds seconds for ii-agent readiness."

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastWslIp = $null
    $lastState = $null
    $lastServiceStart = Get-Date
    $readyCount = 0
    $readyIp = $null

    while ((Get-Date) -lt $deadline) {
        try {
            $wslIp = Get-WslIpAddress
        } catch {
            Write-Log "WSL IP lookup failed; retrying: $($_.Exception.Message)"
            $wslIp = $null
        }
        if (-not $wslIp) {
            $readyCount = 0
            if ($lastState -ne "wsl-ip-unavailable") {
                Write-Log "WSL has not assigned an IPv4 address yet."
                $lastState = "wsl-ip-unavailable"
            }
            Start-Sleep -Seconds $PollIntervalSeconds
            continue
        }

        $backendReady = Test-HttpStatus -Uri "http://${wslIp}:8000/health/ready"
        $frontendReady = Test-HttpStatus -Uri "http://${wslIp}:1420/"
        $bootComplete = $false
        $unitStates = @()
        try {
            $systemState = Invoke-WslCommand -Arguments '-u root -- systemctl is-system-running'
            $bootComplete = -not $systemState.TimedOut -and $systemState.Output.Trim() -match '^(running|degraded)$'
            if ($bootComplete) {
                $units = Invoke-WslCommand -Arguments '-u root -- systemctl show -p ActiveState --value docker.service ii-agent-local.service'
                if (-not $units.TimedOut -and $units.ExitCode -eq 0) {
                    $unitStates = @($units.Output.Trim() -split '\s+')
                }
            }
        } catch {
            Write-Log "Linux service status unavailable; retrying: $($_.Exception.Message)"
        }
        $unitsActive = $unitStates.Count -eq 2 -and $unitStates[0] -eq 'active' -and $unitStates[1] -eq 'active'
        if ($bootComplete -and $unitStates.Count -eq 2 -and
            $unitStates -notcontains 'activating' -and $unitStates -notcontains 'deactivating' -and
            ($unitStates -contains 'inactive' -or $unitStates -contains 'failed') -and
            (Get-Date) -ge $lastServiceStart.AddSeconds(120)) {
            $lastServiceStart = Get-Date
            try {
                $startResult = Invoke-WslCommand -Arguments '-u root -- /bin/sh -c "if test -e /tmp/.ii-agent-rebuild-lock; then exit 0; fi; systemctl start docker.service ii-agent-local.service"' -TimeoutMilliseconds 90000
                if ($startResult.TimedOut -or $startResult.ExitCode -ne 0) {
                    Write-Log "Linux service start attempt failed or timed out; retrying. $($startResult.Error.Trim())"
                }
            } catch {
                Write-Log "Linux service start attempt failed; retrying: $($_.Exception.Message)"
            }
        }
        $stackReady = $false
        if ($backendReady -and $frontendReady -and $bootComplete -and $unitsActive) {
            try {
                $status = Invoke-WslCommand -Arguments "-u $linuxUser -- /home/mdear/workspaces/git/ii-agent/scripts/stack_control.sh status --ready --timeout 0" -TimeoutMilliseconds 60000
                $stackReady = -not $status.TimedOut -and $status.ExitCode -eq 0
            } catch {
                Write-Log "Linux stack readiness unavailable; retrying: $($_.Exception.Message)"
            }
        }
        if (-not $stackReady) {
            $readyCount = 0
            $state = "boot=$bootComplete units=$($unitStates -join ',') backend=$backendReady frontend=$frontendReady stack=$stackReady"
            if ($state -ne $lastState) {
                Write-Log "Waiting for ii-agent readiness: $state."
                $lastState = $state
            }
            Start-Sleep -Seconds $PollIntervalSeconds
            continue
        }
        if ($wslIp -ne $readyIp) {
            $readyIp = $wslIp
            $readyCount = 0
        }
        $readyCount++
        if ($readyCount -lt 3) {
            Start-Sleep -Seconds $PollIntervalSeconds
            continue
        }
        try {
            Ensure-IpHelper
            if ($wslIp -ne $lastWslIp) {
                Set-PortProxy -WslIp $wslIp
                $lastWslIp = $wslIp
            }
        } catch {
            Write-Log "Windows forwarding not ready: $($_.Exception.Message)"
            Start-Sleep -Seconds $PollIntervalSeconds
            continue
        }

        Write-Log "ii-agent is ready; frontend and backend are reachable through $wslIp."
        exit 0
    }

    Write-Log "Timed out waiting for ii-agent readiness after $TimeoutSeconds seconds."
    exit 1
} catch {
    Write-Log "Monitor failed: $($_.Exception.Message)"
    exit 1
}