param([string]$PythonExe = 'python')
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
& $PythonExe -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Instale Python 3.11+ com pip.' }
& ./.venv/Scripts/python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Falha nas dependências Python.' }
& npm.cmd install
if ($LASTEXITCODE -ne 0) { throw 'Falha nas dependências npm.' }
& npm.cmd run css
if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar CSS.' }
Write-Host 'Configure OPENAI_API_KEY e execute npm run dev.'
