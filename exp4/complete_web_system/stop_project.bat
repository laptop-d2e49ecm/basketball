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
$PythonExe = Join-Path $Root 'backend\.venv\Scripts\python.exe'
$ProcessHelper = Join-Path $Root 'service_processes.py'
$Entries = @()
if (Test-Path -LiteralPath $ManifestPath) {
    try {
        $Saved = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($Saved.PSObject.Properties.Name -contains 'value') { $Saved = $Saved.value }
        $Entries = @($Saved)
    } catch { Write-Host 'Recovering services from process ownership...' }
}
$Json = & $PythonExe $ProcessHelper list
if ($LASTEXITCODE -ne 0) { Write-Host 'Cannot inspect services. Install backend requirements.txt.'; exit 1 }
foreach ($Row in ($Json | ConvertFrom-Json)) {
    if (-not ($Entries | Where-Object { $_.Id -eq $Row.id })) {
        $Process = Get-Process -Id ([int]$Row.id) -ErrorAction SilentlyContinue
        if ($Process) { $Entries += [pscustomobject]@{ Service=$Row.service; Id=$Process.Id; ProcessName=$Process.ProcessName; StartTimeTicks=[string]$Process.StartTime.ToUniversalTime().Ticks } }
    }
}

for ($Index = $Entries.Count - 1; $Index -ge 0; $Index--) {
    $Entry = $Entries[$Index]
    try {
        $Process = Get-Process -Id ([int]$Entry.Id) -ErrorAction Stop
        $SameProcess = $Process.ProcessName -eq [string]$Entry.ProcessName
        $SameStartTime = [string]$Process.StartTime.ToUniversalTime().Ticks -eq [string]$Entry.StartTimeTicks
        if ($SameProcess -and $SameStartTime) {
            & $PythonExe $ProcessHelper stop --pid ([string]$Process.Id)
            if ($LASTEXITCODE -ne 0) { throw 'Project service could not be stopped.' }
            Write-Host "Stopped $($Entry.Service)."
        }
    } catch {
        if (Get-Process -Id ([int]$Entry.Id) -ErrorAction SilentlyContinue) {
            Write-Host ('停止失败：' + $_.Exception.Message) -ForegroundColor Red
            exit 1
        }
    }
}

Remove-Item -LiteralPath $ManifestPath -Force -ErrorAction SilentlyContinue
Write-Host 'Launcher-managed services have been stopped.'
