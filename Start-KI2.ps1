param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$projectDir = $PSScriptRoot
$scriptPath = Join-Path $projectDir 'KI.py'
$databasePath = Join-Path $projectDir 'KI.matrix.sqlite3'
$pythonPath = 'C:\Users\szela\miniconda3\python.exe'
foreach ($requiredPath in @($scriptPath, $databasePath, $pythonPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) { throw "Brak pliku: $requiredPath" }
}
$scannerProcesses = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -and
    $_.CommandLine.Contains($scriptPath) -and $_.CommandLine.Contains($databasePath) -and
    $_.CommandLine -match '--scanner(?:\s|$)'
})
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
$launcher = Start-Process -FilePath $pythonPath -ArgumentList $startArgs -WorkingDirectory $projectDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectDir 'KI.production-launcher.stdout.log') -RedirectStandardError (Join-Path $projectDir 'KI.production-launcher.stderr.log')
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
