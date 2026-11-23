$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "weekly_check.bat"
$name = "Vetera Intelligence - wekelijkse broncontrole"
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$script`""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 9am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Description "Controleert bronnen van Vetera Intelligence (robots.txt wordt gerespecteerd)." -Force | Out-Null
Write-Host "Taak '$name' is ingepland (maandag 09:00, inhalen wanneer de computer weer aan staat)."
