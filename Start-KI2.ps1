param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$projectDir = $PSScriptRoot
$scriptPath = Join-Path $projectDir 'KI.py'
$pythonPath = 'C:\Users\szela\miniconda3\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) { throw 'Brak interpretera KI 2.' }
$pathsJson = & $pythonPath -B -X utf8 (Join-Path $projectDir 'ki2_paths.py') --project $projectDir
if ($LASTEXITCODE -ne 0) { throw 'Nie można odczytać ścieżek KI 2.' }
$runtimePaths = $pathsJson | ConvertFrom-Json
$databasePath = $runtimePaths.database
$logDir = $runtimePaths.log_dir
foreach ($requiredPath in @($scriptPath, $databasePath, $pythonPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) { throw "Brak pliku: $requiredPath" }
}
$scannerProcesses = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -and
    $_.CommandLine.Contains($scriptPath) -and
    $_.CommandLine -match '--scanner(?:\s|$)'
})
if (@($scannerProcesses | Where-Object { -not $_.CommandLine.Contains($databasePath) }).Count) { throw 'Skaner KI 2 używa innej bazy. Nie uruchomiono drugiej instancji.' }
$health = $false
try { $health = (Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8501/_stcore/health' -TimeoutSec 4).StatusCode -eq 200 } catch {}
if ($scannerProcesses.Count -gt 1) { throw 'Wykryto wiele skanerów KI 2. Wymagana kontrola; nie uruchomiono kolejnego.' }
if ($scannerProcesses.Count -eq 1 -and $health) {
    [pscustomobject]@{ status='ALREADY_RUNNING'; project=$projectDir; scanner_pid=$scannerProcesses[0].ProcessId; panel='http://127.0.0.1:8501/' } | ConvertTo-Json
    exit 0
}
if ($scannerProcesses.Count -or $health) { throw 'Niespójny stan panelu i skanera. Nie uruchomiono drugiej instancji.' }
if ($CheckOnly) {
    [pscustomobject]@{ status='READY_TO_START'; project=$projectDir; database=$databasePath; python=$pythonPath } | ConvertTo-Json
    exit 0
}
$startArgs = '-B -X utf8 -u "' + $scriptPath + '" --start --no-browser --db "' + $databasePath + '"'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$launcher = Start-Process -FilePath $pythonPath -ArgumentList $startArgs -WorkingDirectory $projectDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir 'KI.production-launcher.stdout.log') -RedirectStandardError (Join-Path $logDir 'KI.production-launcher.stderr.log')
$deadline = (Get-Date).AddSeconds(50)
do {
    Start-Sleep -Milliseconds 500
    $launcher.Refresh()
    if ($launcher.HasExited) { throw 'Launcher zakończył pracę. Sprawdź KI.production-launcher.stderr.log.' }
    $children = @(Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $launcher.Id -and $_.CommandLine -and $_.CommandLine.Contains($scriptPath) })
    $scannerReady = @($children | Where-Object { $_.CommandLine -match '--scanner(?:\s|$)' }).Count -eq 1
    try { $health = (Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8501/_stcore/health' -TimeoutSec 2).StatusCode -eq 200 } catch { $health = $false }
    if ($scannerReady -and $health) {
        [pscustomobject]@{ status='STARTED'; project=$projectDir; launcher_pid=$launcher.Id; panel='http://127.0.0.1:8501/' } | ConvertTo-Json
        exit 0
    }
} while ((Get-Date) -lt $deadline)
throw 'Start niepotwierdzony w ciągu 50 sekund. Nie ponawiaj przed sprawdzeniem procesów i logów.'
