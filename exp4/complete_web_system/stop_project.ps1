$ErrorActionPreference = 'Stop'

$RuntimeDir = Join-Path $PSScriptRoot '.runtime'
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
