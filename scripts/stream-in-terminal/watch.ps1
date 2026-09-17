# Launch stream-in-terminal after checking external dependencies (Windows).
# Usage: .\watch.ps1 oMeiaUm --fps 12 --quality 480p
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Die([string]$Message) {
    [Console]::Error.WriteLine("error: $Message")
    exit 1
}

function Have([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

$Python = $null
$PythonPrefix = @()
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $Python = $VenvPython
    $env:PATH = "$(Join-Path $Root '.venv\Scripts');$env:PATH"
} else {
    foreach ($cand in @("python", "py")) {
        if (Have $cand) {
            if ($cand -eq "py") {
                $Python = "py"
                $PythonPrefix = @("-3")
            } else {
                $Python = "python"
                $PythonPrefix = @()
            }
            break
        }
    }
}
if (-not $Python) {
    Die "Python 3 is required but was not found on PATH."
}

& $Python @PythonPrefix -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) {
    Die "Python 3.10+ is required."
}

if (-not (Have "ffmpeg")) {
    Die "ffmpeg not found. Install ffmpeg and ensure it is on PATH."
}

$hasResolver = $false
if ((Have "streamlink") -or (Have "yt-dlp") -or (Have "yt_dlp")) {
    $hasResolver = $true
} else {
    & $Python @PythonPrefix -c "import streamlink" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $hasResolver = $true }
    if (-not $hasResolver) {
        & $Python @PythonPrefix -c "import yt_dlp" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $hasResolver = $true }
    }
}
if (-not $hasResolver) {
    Die "Need streamlink (preferred) or yt-dlp (pip install streamlink)."
}

& $Python @PythonPrefix -c "import stream_in_terminal" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    $src = Join-Path $Root "src"
    if ($env:PYTHONPATH) {
        $env:PYTHONPATH = "$src;$env:PYTHONPATH"
    } else {
        $env:PYTHONPATH = $src
    }
}

& $Python @PythonPrefix -m stream_in_terminal @args
exit $LASTEXITCODE
