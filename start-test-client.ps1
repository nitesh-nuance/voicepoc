# Azure Communication Services Test Client Launcher
# This script starts a local web server to serve the test client without CORS issues

Write-Host "===========================================" -ForegroundColor Cyan
Write-Host "Azure Communication Services Test Client" -ForegroundColor Cyan
Write-Host "===========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Starting local web server for CORS-free testing..." -ForegroundColor Yellow
Write-Host ""
Write-Host "After the server starts:" -ForegroundColor Green
Write-Host "1. Open http://localhost:8000/test-client-local-server.html" -ForegroundColor White
Write-Host "2. Click 'Initialize Client' to start" -ForegroundColor White
Write-Host "3. Get a token and test voice calls" -ForegroundColor White
Write-Host ""
Write-Host "Press Ctrl+C to stop the server when done." -ForegroundColor Red
Write-Host ""

# Check if Python is available
try {
    $pythonVersion = python --version 2>&1
    Write-Host "Using Python: $pythonVersion" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "Error: Python not found. Please install Python 3.x" -ForegroundColor Red
    Write-Host "Download from: https://www.python.org/downloads/" -ForegroundColor Yellow
    pause
    exit 1
}

# Start the server
try {
    python serve-test-client.py
} catch {
    Write-Host ""
    Write-Host "Server stopped." -ForegroundColor Yellow
}
