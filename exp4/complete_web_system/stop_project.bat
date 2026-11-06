@echo off
setlocal DisableDelayedExpansion
set "COURTVISION_SCRIPT_PATH=%~f0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$source = [System.IO.File]::ReadAllText($env:COURTVISION_SCRIPT_PATH, [System.Text.Encoding]::UTF8); $payload = ($source -split '(?m)^#==COURTVISION_POWERSHELL==\r?$', 2)[1]; if (-not $payload) { throw 'Launcher payload is missing.' }; & ([scriptblock]::Create($payload))"
set "COURTVISION_EXIT_CODE=%errorlevel%"
if not "%COURTVISION_EXIT_CODE%"=="0" pause
exit /b %COURTVISION_EXIT_CODE%

#==COURTVISION_POWERSHELL==
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $env:COURTVISION_SCRIPT_PATH
$RuntimeDir = Join-Path $Root '.runtime'
$ManifestPath = Join-Path $RuntimeDir 'services.json'
if (-not (Test-Path -LiteralPath $ManifestPath)) {
    Write-Host 'No launcher-managed services are running.'
    exit 0
}

try {
    $Entries = @(Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json)
} catch {
    Write-Error 'The service list could not be read. Remove .runtime\services.json after checking running processes.'
    exit 1
}

for ($Index = $Entries.Count - 1; $Index -ge 0; $Index--) {
    $Entry = $Entries[$Index]
    try {
        $Process = Get-Process -Id ([int]$Entry.Id) -ErrorAction Stop
        $SameProcess = $Process.ProcessName -eq [string]$Entry.ProcessName
        $SameStartTime = [string]$Process.StartTime.ToUniversalTime().Ticks -eq [string]$Entry.StartTimeTicks
        if ($SameProcess -and $SameStartTime) {
            Stop-Process -Id $Process.Id -Force
            Write-Host "Stopped $($Entry.Service)."
        }
    } catch {
        # The process already exited or its PID has been reused; leave it alone.
    }
}

Remove-Item -LiteralPath $ManifestPath -Force -ErrorAction SilentlyContinue
Write-Host 'Launcher-managed services have been stopped.'
