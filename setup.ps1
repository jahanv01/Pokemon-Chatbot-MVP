# One-step setup for Windows PowerShell: creates the venv, installs packages, writes .env (asking for your keys) and starts the app.
# Usage:  powershell -ExecutionPolicy Bypass -File .\setup.ps1            (set up and run)
#         powershell -ExecutionPolicy Bypass -File .\setup.ps1 -NoRun     (set up only)
param([switch]$NoRun)  # -NoRun = do the setup but do not start the server
$ErrorActionPreference = "Stop"  # stop on the first error

Set-Location $PSScriptRoot  # always work from the project folder, wherever the script is called from

# ---- 1. find a working Python 3.12+ ----
$py = $null  # will hold the python command we use
foreach ($cmd in @("python", "python3", "py")) {  # try the common names (py = Windows launcher)
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { continue }  # not installed under this name
    try {
        & $cmd -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" 2>$null  # works and is new enough?
        if ($LASTEXITCODE -eq 0) { $py = $cmd; break }  # remember it and stop looking
    } catch { }  # ignore stubs such as the Microsoft Store placeholder
}
if (-not $py) {  # nothing suitable found
    throw "Python 3.12 or newer is required. Install it from https://www.python.org/downloads/ and run this again."
}

# ---- 2. virtual environment + dependencies ----
if (-not (Test-Path ".venv")) {  # only create it the first time
    Write-Host "Creating virtual environment..."
    & $py -m venv .venv  # new isolated environment in .\.venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the virtual environment." }
}
$venvPy = ".venv\Scripts\python.exe"  # the environment's own python
Write-Host "Installing packages (this can take a minute)..."
& $venvPy -m pip install -q -r requirements.txt  # install everything the app needs
if ($LASTEXITCODE -ne 0) { throw "pip install failed. See the message above." }

# ---- 3. .env (ask for the three values) ----
function Read-Secret([string]$prompt) {  # ask without echoing what is typed
    $secure = Read-Host $prompt -AsSecureString  # hidden input
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)  # unwrap it
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }  # plain text for the .env writer
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }  # wipe the temporary copy
}

$writeEnv = $true  # assume we need to create it
if (Test-Path ".env") {  # never overwrite an existing config silently
    $keep = Read-Host ".env already exists. Keep it? [Y/n]"  # ask the user
    if ($keep -notmatch "^[nN]") { $writeEnv = $false }  # only rewrite if they say no
}

if ($writeEnv) {
    $prompted = @()  # names we set ourselves, so we can clear them afterwards
    Write-Host "Get a free Gemini key at https://aistudio.google.com/apikey"
    if (-not $env:GOOGLE_API_KEY) {  # skip the prompt if it is already set in the environment
        while (-not $env:GOOGLE_API_KEY) { $env:GOOGLE_API_KEY = Read-Secret "Gemini API key (hidden)" }  # ask until something is entered
        $prompted += "GOOGLE_API_KEY"
    }
    if (-not $env:APP_ACCESS_USERNAME) {  # username for the chat login
        while (-not $env:APP_ACCESS_USERNAME) { $env:APP_ACCESS_USERNAME = Read-Host "Choose a chat username" }
        $prompted += "APP_ACCESS_USERNAME"
    }
    if (-not $env:APP_ACCESS_PASSWORD) {  # password for the chat login
        while (-not $env:APP_ACCESS_PASSWORD) { $env:APP_ACCESS_PASSWORD = Read-Secret "Choose a chat password (hidden)" }
        $prompted += "APP_ACCESS_PASSWORD"
    }
    & $venvPy scripts\make_env.py  # builds .env from .env.example, quoting special characters safely
    if ($LASTEXITCODE -ne 0) { throw "Could not write .env." }
    foreach ($name in $prompted) { Remove-Item "Env:$name" }  # do not leave the secrets in this PowerShell session
    Write-Host ".env written."
}

# ---- 4. run ----
if ($NoRun) {  # setup only
    Write-Host "Setup done. Start the app with:  $venvPy -m uvicorn app.main:app"
    return
}
Write-Host "Starting the app at http://127.0.0.1:8000  (press Ctrl+C to stop)"
& $venvPy -m uvicorn app.main:app  # run the server in this terminal
