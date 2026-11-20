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
$BackendDir = Join-Path $Root 'backend'
$FrontendDir = Join-Path $Root 'frontend'
$RuntimeDir = Join-Path $Root '.runtime'
$LogDir = Join-Path $RuntimeDir 'logs'
$ManifestPath = Join-Path $RuntimeDir 'services.json'
$PythonExe = Join-Path $BackendDir '.venv\Scripts\python.exe'
$ViteCli = Join-Path $FrontendDir 'node_modules\vite\bin\vite.js'
$ProcessHelper = Join-Path $Root 'service_processes.py'
$FrontendUrl = 'http://127.0.0.1:5173/'
$ApiHealthUrl = 'http://127.0.0.1:8000/api/v1/health'

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

function Test-ManagedProcess($Entry) {
    try {
        $Process = Get-Process -Id ([int]$Entry.Id) -ErrorAction Stop
        if ($Process.ProcessName -ne [string]$Entry.ProcessName) { return $false }
        return ([string]$Process.StartTime.ToUniversalTime().Ticks -eq [string]$Entry.StartTimeTicks)
    } catch {
        return $false
    }
}

function Save-Manifest {
    if ($script:ManagedEntries.Count -gt 0) {
        $script:ManagedEntries | ConvertTo-Json -Depth 4 |
            Set-Content -LiteralPath $ManifestPath -Encoding UTF8
    } elseif (Test-Path -LiteralPath $ManifestPath) {
        Remove-Item -LiteralPath $ManifestPath -Force
    }
}

function Quote-Argument([string]$Value) {
    return '"' + $Value.Replace('"', '\"') + '"'
}

function Find-Node {
    $Command = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($Command) { return $Command.Source }

    $Candidates = @(
        (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'),
        (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\node.exe'),
        'C:\Program Files\nodejs\node.exe'
    )
    foreach ($Candidate in $Candidates) {
        if (Test-Path -LiteralPath $Candidate) { return $Candidate }
    }
    return $null
}

function Get-ApiHealth {
    try {
        return Invoke-RestMethod -Uri $ApiHealthUrl -TimeoutSec 2
    } catch {
        return $null
    }
}

function Test-CurrentApiEndpoints {
    try {
        $Schema = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/openapi.json' -TimeoutSec 2
        $TaskPath = $Schema.paths.PSObject.Properties['/api/v1/tasks/{task_id}'].Value
        $ImagePath = $Schema.paths.PSObject.Properties['/api/v1/agent/images'].Value
        return ($null -ne $TaskPath -and $null -ne $TaskPath.delete -and $null -ne $ImagePath -and $null -ne $ImagePath.post)
    } catch {
        return $false
    }
}

function Test-ApiReady {
    $Response = Get-ApiHealth
    return (
        $Response -and
        $Response.code -eq 0 -and
        $Response.result.status -eq 'ok' -and
        (Test-CurrentApiEndpoints)
    )
}

function Test-FrontendReady {
    try {
        $Response = Invoke-WebRequest -UseBasicParsing -Uri $FrontendUrl -TimeoutSec 2
        return ($Response.StatusCode -eq 200 -and $Response.Content.Contains('CourtVision'))
    } catch {
        return $false
    }
}

function Get-OwnedEntries {
    $Json = & $PythonExe $ProcessHelper list
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect project services. Install backend requirements.txt (psutil is required).' }
    foreach ($Row in ($Json | ConvertFrom-Json)) {
        try {
            $Process = Get-Process -Id ([int]$Row.id) -ErrorAction Stop
            [pscustomobject]@{
                Service = $Row.service; Id = $Process.Id; ProcessName = $Process.ProcessName
                StartTimeTicks = [string]$Process.StartTime.ToUniversalTime().Ticks
                Stdout = $null; Stderr = $null; Ports = @($Row.ports)
            }
        } catch { }
    }
}

function Stop-Entry($Entry) {
    if (Test-ManagedProcess $Entry) {
        & $PythonExe $ProcessHelper stop --pid ([string]$Entry.Id)
        if ($LASTEXITCODE -ne 0) { throw "Cannot stop project service $($Entry.Service)." }
    }
}

function Start-HiddenService([string]$Name, [string]$FilePath, [string[]]$Arguments, [string]$WorkingDirectory) {
    $Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $StdoutPath = Join-Path $LogDir "$Name-$Stamp.out.log"
    $StderrPath = Join-Path $LogDir "$Name-$Stamp.err.log"
    $ArgumentLine = (($Arguments | ForEach-Object { Quote-Argument ([string]$_) }) -join ' ')
    $Process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentLine `
        -WorkingDirectory $WorkingDirectory -WindowStyle Hidden `
        -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath -PassThru
    Start-Sleep -Milliseconds 250
    $Process.Refresh()
    if ($Process.HasExited) {
        $Details = if (Test-Path -LiteralPath $StderrPath) { Get-Content -LiteralPath $StderrPath -Tail 25 | Out-String } else { '' }
        throw "$Name exited during startup.`n$Details"
    }

    $Entry = [pscustomobject]@{
        Service = $Name
        Id = $Process.Id
        ProcessName = $Process.ProcessName
        StartTimeTicks = [string]$Process.StartTime.ToUniversalTime().Ticks
        Stdout = $StdoutPath
        Stderr = $StderrPath
    }
    $script:ManagedEntries += $Entry
    $script:NewEntries += $Entry
    Save-Manifest
    Write-Host "Started $Name in the background."
    return $Entry
}

function Wait-ForService([scriptblock]$Check, [string]$Name, [int]$TimeoutSeconds, $Entry) {
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $Deadline) {
        if (& $Check) { return }
        if ($Entry -and -not (Test-ManagedProcess $Entry)) {
            $Details = if (Test-Path -LiteralPath $Entry.Stderr) { Get-Content -LiteralPath $Entry.Stderr -Tail 30 | Out-String } else { '' }
            throw "$Name stopped before becoming ready.`n$Details"
        }
        Start-Sleep -Seconds 1
    }
    $Details = if ($Entry -and (Test-Path -LiteralPath $Entry.Stderr)) { Get-Content -LiteralPath $Entry.Stderr -Tail 30 | Out-String } else { '' }
    throw "$Name did not become ready in time.`n$Details"
}

$script:ManagedEntries = @()
$script:NewEntries = @()
if (Test-Path -LiteralPath $ManifestPath) {
    try {
        $SavedDocument = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($SavedDocument.PSObject.Properties.Name -contains 'value') { $SavedDocument = $SavedDocument.value }
        $SavedEntries = @($SavedDocument)
        foreach ($Entry in $SavedEntries) {
            if (Test-ManagedProcess $Entry) { $script:ManagedEntries += $Entry }
        }
    } catch {
        $script:ManagedEntries = @()
    }
}

try {
    if (-not (Test-Path -LiteralPath $PythonExe)) {
        throw "Backend environment is missing: $PythonExe. Install it using README.md first."
    }
    if (-not (Test-Path -LiteralPath $ViteCli)) {
        throw "Frontend dependencies are missing. Install them in the frontend folder first."
    }
    $NodeExe = Find-Node
    if (-not $NodeExe) {
        throw 'Node.js was not found. Install Node.js 20.19+ or add node.exe to PATH.'
    }
    $env:Path = (Split-Path -Parent $NodeExe) + ';' + $env:Path
    # Recover services even when the manifest was lost; identify by cwd and command.
    foreach ($Entry in @(Get-OwnedEntries)) {
        if (-not ($script:ManagedEntries | Where-Object { $_.Id -eq $Entry.Id })) { $script:ManagedEntries += $Entry }
    }
    Save-Manifest


    $ApiHealth = Get-ApiHealth
    $ExistingApi = Test-ApiReady
    $ApiEntry = $null
    if (-not $ExistingApi) {
        if ($ApiHealth -and $ApiHealth.code -eq 0 -and $ApiHealth.result.status -eq 'ok') {
            $ApiOwners = @(Get-OwnedEntries | Where-Object { $_.Service -eq 'api' -and $_.Ports -contains 8000 })
            if ($ApiOwners.Count -ne 1) { throw 'Port 8000 is occupied by an unrecognized service. Stop that service before starting this project.' }
            $TaskOffset = 0
            do {
                $Tasks = Invoke-RestMethod -Uri ("http://127.0.0.1:8000/api/v1/tasks?limit=200&offset=" + $TaskOffset) -TimeoutSec 5
                if (@($Tasks.result | Where-Object { $_.status -in @('running', 'pending') }).Count) {
                    throw 'Video tasks are active. Wait for them to finish before restarting the old backend.'
                }
                $TaskOffset += 200
            } while (@($Tasks.result).Count -eq 200)
            Write-Host 'Updating the old project backend...'
            Stop-Entry $ApiOwners[0]
            $script:ManagedEntries = @($script:ManagedEntries | Where-Object { Test-ManagedProcess $_ })
            Save-Manifest
        }
        $ApiEntry = Start-HiddenService 'api' $PythonExe @(
            '-u', '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000', '--app-dir', $BackendDir
        ) $BackendDir
    }

    $WorkerEntry = $script:ManagedEntries | Where-Object { $_.Service -eq 'worker' } | Select-Object -First 1
    if (-not $WorkerEntry) {
        $WorkerEntry = Start-HiddenService 'worker' $PythonExe @('-u', '-m', 'worker.main') $BackendDir
    } elseif ($WorkerEntry) {
        Write-Host 'Worker is already running.'
    } else {
        Write-Host 'An existing Worker process was found; reusing it.'
    }

    $ExistingFrontend = Test-FrontendReady
    $FrontendEntry = $null
    if (-not $ExistingFrontend) {
        $FrontendEntry = Start-HiddenService 'frontend' $NodeExe @($ViteCli, '--host', '127.0.0.1', '--strictPort') $FrontendDir
    }

    Wait-ForService { Test-ApiReady } 'Backend API' 60 $ApiEntry
    Wait-ForService { Test-FrontendReady } 'Frontend' 90 $FrontendEntry

    if ($WorkerEntry -and $WorkerEntry.Stderr) {
        $Deadline = (Get-Date).AddSeconds(180)
        $WorkerReady = $false
        while ((Get-Date) -lt $Deadline) {
            if (Test-Path -LiteralPath $WorkerEntry.Stderr) {
                $WorkerLog = Get-Content -LiteralPath $WorkerEntry.Stderr -Raw -ErrorAction SilentlyContinue
                if ($WorkerLog -match 'Worker is ready; polling for tasks') { $WorkerReady = $true; break }
            }
            if (-not (Test-ManagedProcess $WorkerEntry)) {
                $Details = if (Test-Path -LiteralPath $WorkerEntry.Stderr) { Get-Content -LiteralPath $WorkerEntry.Stderr -Tail 30 | Out-String } else { '' }
                throw "Worker stopped during startup.`n$Details"
            }
            Start-Sleep -Seconds 1
        }
        if (-not $WorkerReady) {
            $Details = if (Test-Path -LiteralPath $WorkerEntry.Stderr) { Get-Content -LiteralPath $WorkerEntry.Stderr -Tail 30 | Out-String } else { '' }
            throw "Worker did not become ready in time.`n$Details"
        }
    }

    Save-Manifest
    Write-Host "All services are ready: $FrontendUrl"
    if ($env:COURTVISION_NO_BROWSER -ne '1') { Start-Process -FilePath $FrontendUrl }
} catch {
    Write-Host ('启动失败：' + $_.Exception.Message) -ForegroundColor Red
    for ($Index = $script:NewEntries.Count - 1; $Index -ge 0; $Index--) {
        Stop-Entry $script:NewEntries[$Index]
    }
    $script:ManagedEntries = @($script:ManagedEntries | Where-Object { Test-ManagedProcess $_ })
    Save-Manifest
    exit 1
}
