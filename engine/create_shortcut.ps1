param([Parameter(Mandatory=$true)][string]$Target, [Parameter(Mandatory=$true)][string]$LinkPath)
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($LinkPath)
$shortcut.TargetPath = $Target
$shortcut.WorkingDirectory = Split-Path -LiteralPath $Target
$shortcut.Description = 'CAD Toolkit'
$shortcut.Save()
