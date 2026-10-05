$ErrorActionPreference = 'Stop'
$projektKI = $PSScriptRoot
$wymaganiaKI = Join-Path $projektKI 'requirements-tradingagents.txt'
$srodowiskoKI = Join-Path $projektKI 'KI_tradingagents_env'
$pythonKI = Join-Path $srodowiskoKI 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $wymaganiaKI)) { throw 'Brak requirements-tradingagents.txt obok tego skryptu.' }
if (-not (Test-Path -LiteralPath $pythonKI)) {
    python -m venv $srodowiskoKI
    if ($LASTEXITCODE -ne 0) { throw 'Nie udalo sie utworzyc osobnego srodowiska TradingAgents.' }
}
& $pythonKI -m pip install -r $wymaganiaKI
if ($LASTEXITCODE -ne 0) { throw 'Instalacja TradingAgents nie powiodla sie. Skaner pozostaje niezalezny.' }
& $pythonKI (Join-Path $projektKI 'Napraw-TradingAgents.py')
if ($LASTEXITCODE -ne 0) { throw 'Poprawka narzedzi Yahoo nie powiodla sie.' }
& $pythonKI -c "import tradingagents; from tradingagents.graph.trading_graph import TradingAgentsGraph; assert tradingagents.__version__ == '0.6.0'; print('TradingAgents 0.6.0: instalacja poprawna')"
if ($LASTEXITCODE -ne 0) { throw 'Weryfikacja TradingAgents nie powiodla sie.' }
Write-Host 'Gotowe. W panelu wybierz Analiza poglebiona. Korzysta z OPENAI_API_KEY zapisanej przy KI.py.'
