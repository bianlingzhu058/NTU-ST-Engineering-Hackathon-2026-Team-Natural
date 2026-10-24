# One-time VM setup (run by the operator, not by the bot): put a "DeskAssist" shortcut on the Desktop
# that starts the operator window with the REAL pythonw.exe. No renamed copy of Python, so Sysmon's
# Image and OriginalFileName agree (judges' feedback 21 Oct), and pythonw has no console, so no
# conhost.exe child. Double-clicking the shortcut makes explorer.exe the parent.
#   powershell -ExecutionPolicy Bypass -File C:\Finals\app\tools\make_shortcut.ps1
param([string]$App = (Split-Path -Parent $PSScriptRoot))
$candidates = @(
  (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source,
  "$env:LOCALAPPDATA\Programs\Python\Python312\pythonw.exe",
  "C:\Program Files\Python312\pythonw.exe",
  "C:\Python312\pythonw.exe"
) | Where-Object { $_ -and (Test-Path $_) }
if (-not $candidates) { Write-Host "pythonw.exe not found. Install Python 3.12 first." -ForegroundColor Red; exit 1 }
$py = @($candidates)[0]
$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'DeskAssist.lnk'
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$s.TargetPath = $py
$s.Arguments = '-m ui'
$s.WorkingDirectory = $App
$s.WindowStyle = 1
$s.Description = 'Synthetic activity harness (authorised test VMs only)'
$s.Save()
Write-Host "Shortcut: $lnk" -ForegroundColor Green
Write-Host "  target: $py -m ui" -ForegroundColor Green
Write-Host "  start in: $App" -ForegroundColor Green
