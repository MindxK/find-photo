$ErrorActionPreference = 'Stop'
$projectDirectory = $PSScriptRoot
$pythonExecutable = Join-Path $projectDirectory '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) { throw 'Run Install-FindFace.ps1 first.' }
$serverScript = Join-Path $projectDirectory 'serve.py'
Start-Process -FilePath $pythonExecutable -ArgumentList ('"' + $serverScript + '"') -WorkingDirectory $projectDirectory -WindowStyle Hidden
Write-Host 'FindFace server is starting. Open http://127.0.0.1:8765/login'
