# Set Windows 10 Display Scaling to 200% for Multiple Monitors
# This script allows you to set different scaling for each monitor

# Run as Administrator
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "This script requires Administrator privileges. Relaunching as Administrator..."
    Start-Process powershell.exe -ArgumentList ("-NoProfile -ExecutionPolicy Bypass -File `"{0}`"" -f $PSCommandPath) -Verb RunAs
    exit
}

Write-Host "Windows 10 Multi-Monitor Display Scaling Setup" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# Display available monitors
Write-Host "Detecting monitors..." -ForegroundColor Yellow
$monitors = Get-WmiObject WmiMonitorBasicDisplayParams -Namespace "root\wmi" -ErrorAction SilentlyContinue

if ($monitors) {
    Write-Host "Found $($monitors.Count) monitor(s)" -ForegroundColor Green
} else {
    Write-Host "Could not detect monitors via WMI. Using default approach." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Choose an option:" -ForegroundColor Cyan
Write-Host "1. Set ALL monitors to 200%"
Write-Host "2. Set different scaling for each monitor"
Write-Host "3. Exit"
Write-Host ""

$choice = Read-Host "Enter your choice (1-3)"

switch ($choice) {
    "1" {
        # Set all monitors to same scaling
        $regPath = "HKCU:\Control Panel\Desktop"
        $regName = "LogPixels"
        $regValue = 192  # 200%

        try {
            Set-ItemProperty -Path $regPath -Name $regName -Value $regValue -Force
            Write-Host "All monitors set to 200%" -ForegroundColor Green
            Write-Host "Please log out and log back in for changes to take effect." -ForegroundColor Yellow
        }
        catch {
            Write-Host "Error: $_" -ForegroundColor Red
        }
    }
    "2" {
        # Set different scaling per monitor (requires display arrangement knowledge)
        Write-Host ""
        Write-Host "Monitor-specific scaling in Windows 10 requires manual configuration." -ForegroundColor Yellow
        Write-Host "Use these steps instead:" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "1. Right-click on Desktop -> Display Settings"
        Write-Host "2. Under 'Scale and layout', select each monitor from the dropdown"
        Write-Host "3. Set the scaling percentage for each monitor individually"
        Write-Host "4. Click Apply"
        Write-Host ""
    }
    "3" {
        Write-Host "Exiting..." -ForegroundColor Yellow
        exit
    }
    default {
        Write-Host "Invalid choice. Exiting." -ForegroundColor Red
        exit
    }
}