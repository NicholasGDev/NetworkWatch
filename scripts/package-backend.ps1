$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$pythonExe = Join-Path $PWD '.venv/Scripts/python.exe'
& $pythonExe -c 'import PyInstaller'
if ($LASTEXITCODE -ne 0) {
    & $pythonExe -m pip install 'pyinstaller>=6,<7'
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar PyInstaller.' }
}
& $pythonExe -m PyInstaller --noconfirm --onedir --name netwatch-service --add-data 'app/templates;app/templates' --add-data 'app/static;app/static' backend.py
if ($LASTEXITCODE -ne 0) { throw 'Falha ao empacotar backend.' }
# Limpa o backend anterior para nao empacotar arquivos antigos.
if (Test-Path src-tauri/resources/backend) { Remove-Item src-tauri/resources/backend -Recurse -Force }
New-Item -ItemType Directory -Force src-tauri/resources/backend | Out-Null
Copy-Item -Path dist/netwatch-service/* -Destination src-tauri/resources/backend -Recurse -Force
