# Run the LangGraph bot natively (Windows PowerShell).
# Use this in dev — produces verbose logs in the foreground.

$ErrorActionPreference = "Stop"

# Activate venv if it exists.
if (Test-Path ".venv\Scripts\Activate.ps1") {
    . .venv\Scripts\Activate.ps1
} else {
    Write-Error "No .venv found. Run: python -m venv .venv ; .venv\Scripts\activate ; pip install -e ."
    exit 1
}

# Confirm deps are installed.
$missing = pip show openai langgraph fastapi 2>$null | Where-Object { $_ -notmatch "^Name" } | ForEach-Object { $_ }
if (-not (pip show openai 2>$null)) {
    Write-Host "Installing deps..."
    pip install -e . | Out-Host
}

# Start uvicorn. --reload-exclude ".venv/*" prevents WatchFiles from
# tracking every site-packages file (which causes constant reload churn).
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --reload-exclude ".venv/*"