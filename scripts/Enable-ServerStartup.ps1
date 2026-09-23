$ErrorActionPreference = 'Stop'
$projectDirectory = Split-Path -Parent $PSScriptRoot
$startupDirectory = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startupDirectory 'FindFace Server.lnk'
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $projectDirectory '.venv\Scripts\pythonw.exe'
$shortcut.Arguments = '"' + (Join-Path $projectDirectory 'serve.py') + '"'
$shortcut.WorkingDirectory = $projectDirectory
$shortcut.WindowStyle = 7
$shortcut.Description = 'Start FindFace private server after signing into Windows'
$shortcut.Save()
Write-Host 'Enabled FindFace startup at Windows sign-in.'
