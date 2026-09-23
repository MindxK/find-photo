[System.IO.File]::WriteAllText((Join-Path $PSScriptRoot 'data\server-stop'), '')
Write-Host 'Stopping FindFace server...'
