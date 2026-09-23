$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host 'Install uv from https://docs.astral.sh/uv/getting-started/installation/ and run this script again.'
    exit 1
}
uv venv --python 3.12 --cache-dir .uv-cache .venv
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv pip install --python .venv/Scripts/python.exe --cache-dir .uv-cache -r requirements.lock
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host 'Installation complete. Run Start-FindFace.cmd, then open http://127.0.0.1:8765'
