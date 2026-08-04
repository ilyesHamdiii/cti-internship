$ErrorActionPreference = "Continue"
$log = Join-Path $PSScriptRoot "docker-desktop-repair.log"

Start-Transcript -Path $log -Force

Write-Host "=== Docker Desktop virtualization repair ==="
Write-Host "Time: $(Get-Date -Format o)"

$features = @(
    "VirtualMachinePlatform",
    "Microsoft-Windows-Subsystem-Linux",
    "HypervisorPlatform"
)

foreach ($feature in $features) {
    Write-Host "`n--- Checking $feature ---"
    $current = Get-WindowsOptionalFeature -Online -FeatureName $feature
    $current | Select-Object FeatureName, State | Format-Table -AutoSize

    if ($current.State -ne "Enabled") {
        Write-Host "Enabling $feature..."
        Enable-WindowsOptionalFeature -Online -FeatureName $feature -All -NoRestart
    }
}

Write-Host "`n--- Ensuring hypervisor starts automatically ---"
bcdedit /set hypervisorlaunchtype auto

Write-Host "`n--- Final feature states ---"
foreach ($feature in $features) {
    Get-WindowsOptionalFeature -Online -FeatureName $feature |
        Select-Object FeatureName, State |
        Format-Table -AutoSize
}

Write-Host "`nRepair script finished. A Windows restart may be required."
Stop-Transcript
