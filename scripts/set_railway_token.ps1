param([string]$Path = "C:\Users\filip\Downloads\logsrailway.txt")

if (-not (Test-Path $Path)) {
  Write-Output "FILE_NOT_FOUND:$Path"
  exit 1
}

$content = Get-Content -Path $Path -Raw
$token = $null

# Try key=value line first
$match = [regex]::Match($content, 'RAILWAY_TOKEN\s*=\s*([^\r\n]+)')
if ($match.Success) {
  $token = $match.Groups[1].Value.Trim()
}

# Fallback: find a standalone token-like line (long alnum/._-)
if (-not $token) {
  $lines = $content -split "`r?`n"
  foreach ($ln in $lines) {
    if ($ln -match '^[A-Za-z0-9._-]{24,}$') { $token = $ln.Trim(); break }
  }
}

if ($token) {
  $env:RAILWAY_TOKEN = $token
  Write-Output "TOKEN_SET"
  exit 0
} else {
  Write-Output "TOKEN_NOT_SET"
  exit 2
}
