param(
    [Parameter(Mandatory=$true)][string]$PlanPath,
    [Parameter(Mandatory=$true)][string]$ArchiveRoot,
    [string]$ProjectPath = $PSScriptRoot,
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'

function Get-CanonicalDirectory([string]$Path) {
    return (Resolve-Path -LiteralPath $Path -ErrorAction Stop).ProviderPath.TrimEnd('\')
}

function Get-TreeSnapshot([string]$RootPath) {
    $root = Get-CanonicalDirectory $RootPath
    foreach ($item in @(Get-ChildItem -LiteralPath $root -Force -Recurse | Sort-Object FullName)) {
        if ($item.LinkType) { throw 'Dowiązanie w archiwum wymaga osobnej kontroli.' }
        $relative = $item.FullName.Substring($root.Length + 1)
        if ($item.PSIsContainer) {
            [pscustomobject]@{ path=$relative; type='directory'; bytes=0; sha256=$null }
        } else {
            $stamp = $item.LastWriteTimeUtc.Ticks
            $hash = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash
            $item.Refresh()
            if ($item.LastWriteTimeUtc.Ticks -ne $stamp) { throw 'Plik zmienił się podczas kontroli.' }
            [pscustomobject]@{ path=$relative; type='file'; bytes=[long]$item.Length; sha256=$hash }
        }
    }
}

function Assert-SameTree($Expected, $Actual) {
    if (@($Expected).Count -ne @($Actual).Count) { throw 'Niezgodna liczba elementów po przeniesieniu.' }
    $index = @{}
    foreach ($entry in @($Actual)) { $index[$entry.path] = $entry }
    foreach ($entry in @($Expected)) {
        if (-not $index.ContainsKey($entry.path)) { throw 'Brak elementu po przeniesieniu.' }
        $actualEntry = $index[$entry.path]
        if ($entry.type -ne $actualEntry.type -or $entry.bytes -ne $actualEntry.bytes -or $entry.sha256 -ne $actualEntry.sha256) {
            throw 'Niepotwierdzona zgodność danych po przeniesieniu.'
        }
    }
}

$projectRoot = Get-CanonicalDirectory $ProjectPath
$plan = Get-Content -LiteralPath $PlanPath -Raw | ConvertFrom-Json
if ((Get-CanonicalDirectory $plan.source) -ine $projectRoot -or -not (Test-Path -LiteralPath (Join-Path $projectRoot 'KI.py'))) {
    throw 'Plan nie odpowiada projektowi KI 2.'
}
$archivePath = [System.IO.Path]::GetFullPath($ArchiveRoot).TrimEnd('\')
if ($archivePath -ieq $projectRoot -or $archivePath.StartsWith($projectRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or
    $projectRoot.StartsWith($archivePath + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Archiwum musi leżeć poza projektem.'
}
if (Test-Path -LiteralPath $archivePath) { throw 'Cel już istnieje; nie nadpisano archiwum.' }
$parent = Split-Path -Parent $archivePath
if (-not (Test-Path -LiteralPath $parent -PathType Container)) { throw 'Najpierw przygotuj jawny katalog nadrzędny poza OneDrive.' }
if ((Get-CanonicalDirectory $parent) -ine [System.IO.Path]::GetFullPath($parent).TrimEnd('\')) {
    throw 'Katalog nadrzędny archiwum jest przekierowany.'
}
$entries = @($plan.directories)
if (-not $entries.Count) { throw 'Pusty plan.' }
$seen = @{}
$validated = @()
foreach ($entry in $entries) {
    $name = [string]$entry.name
    if ($name -notmatch '^(backup_2026[0-9]{4}_[a-z0-9_]+|audyt-[a-z-]+-2026[0-9]{4}T[0-9]{6}Z|weryfikacja-[a-z-]+-2026[0-9]{4}(T[0-9]{6}Z|-konfiguracja-C)?)$') {
        throw 'Nazwa spoza jawnego zakresu kopii KI.'
    }
    if ($seen.ContainsKey($name)) { throw 'Powtórzona pozycja planu.' }
    $seen[$name] = $true
    $source = Get-CanonicalDirectory (Join-Path $projectRoot $name)
    $destination = [System.IO.Path]::GetFullPath((Join-Path $archivePath $name))
    if ((Split-Path -Parent $source) -ine $projectRoot -or (Split-Path -Parent $destination) -ine $archivePath) {
        throw 'Ścieżka wychodzi poza potwierdzony zakres.'
    }
    $item = Get-Item -LiteralPath $source -Force
    if (-not $item.PSIsContainer -or $item.LinkType) { throw 'Źródło nie jest zwykłym katalogiem.' }
    $files = @(Get-ChildItem -LiteralPath $source -Force -Recurse -File)
    $bytes = [long](($files | Measure-Object -Property Length -Sum).Sum)
    if ($files.Count -ne $entry.files -or $bytes -ne $entry.bytes) { throw 'Inwentarz źródła uległ zmianie.' }
    $tracked = @(& git -C $projectRoot ls-files -- $name)
    if ($LASTEXITCODE -ne 0 -or $tracked.Count) { throw 'Katalog zawiera śledzone pliki lub Git nie potwierdził stanu.' }
    $validated += [pscustomobject]@{ name=$name; source=$source; destination=$destination; bytes=$bytes; files=$files.Count }
}
$busy = @(Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and $_.Name -match '^python(w)?\.exe$' -and
    $_.CommandLine.Contains($projectRoot) -and $_.CommandLine -match 'KI\.py'
})
if ($busy.Count) { throw 'Procesy KI działają lokalnie; przenoszenie wstrzymane.' }
if (-not $Apply) {
    [pscustomobject]@{ status='PLAN_VERIFIED'; source=$projectRoot; destination=$archivePath;
        directories=$validated.Count; bytes=($validated | Measure-Object bytes -Sum).Sum } | ConvertTo-Json
    exit 0
}
New-Item -ItemType Directory -Path $archivePath | Out-Null
if ((Get-CanonicalDirectory $archivePath) -ine $archivePath) { throw 'Windows przekierował nowy cel.' }
$manifest = [ordered]@{ version=1; status='RUNNING'; source=$projectRoot; archive=$archivePath;
    algorithm='SHA256'; records=@(); data_deleted=$false }
$manifestPath = Join-Path $archivePath 'manifest.json'
$position = 0
foreach ($entry in $validated) {
    $position++
    Write-Output ('SHA256 przed: ' + $position + '/' + $validated.Count + ' ' + $entry.name)
    $snapshot = @(Get-TreeSnapshot $entry.source)
    $record = [ordered]@{ name=$entry.name; source=$entry.source; destination=$entry.destination;
        bytes=$entry.bytes; state='PREPARED'; tree=$snapshot }
    $manifest.records += $record
    $manifest | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $manifestPath -Encoding utf8
    # Every absolute source/destination was checked above. Native PowerShell only.
    if (Test-Path -LiteralPath $entry.destination) { throw 'Cel pozycji już istnieje.' }
    Move-Item -LiteralPath $entry.source -Destination $entry.destination
    try {
        Write-Output ('SHA256 po:    ' + $position + '/' + $validated.Count + ' ' + $entry.name)
        $after = @(Get-TreeSnapshot $entry.destination)
        Assert-SameTree $snapshot $after
    } catch {
        if (-not (Test-Path -LiteralPath $entry.source)) {
            Move-Item -LiteralPath $entry.destination -Destination $entry.source
        }
        $record.state = 'ROLLED_BACK'
        $manifest.status = 'STOPPED'
        $manifest | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $manifestPath -Encoding utf8
        throw
    }
    $record.state = 'VERIFIED'
    $manifest | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $manifestPath -Encoding utf8
}
$manifest.status = 'COMPLETE'
$manifest | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $manifestPath -Encoding utf8
[pscustomobject]@{ status='COMPLETE'; directories=$validated.Count;
    bytes=($validated | Measure-Object bytes -Sum).Sum; manifest=$manifestPath; deleted=$false } | ConvertTo-Json
