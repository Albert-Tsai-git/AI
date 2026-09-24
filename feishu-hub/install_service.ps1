# [服务] 注册/卸载 中间服务(FeishuHub) + Claude 执行器(FeishuHubClaudeExecutor) 的开机自启计划任务
# 用法: install_service.ps1            注册并立即启动
#       install_service.ps1 -Uninstall 停止并卸载
param([switch]$Uninstall)
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$tasks = @(
    @{ Name = "FeishuHub"; Args = "-m hub.main" },
    @{ Name = "FeishuHubClaudeExecutor"; Args = "`"$dir\executors\claude\executor.py`"" }
)
if ($Uninstall) {
    foreach ($t in $tasks) {
        Stop-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false -ErrorAction SilentlyContinue
        Write-Output "[服务] 已卸载 $($t.Name)"
    }
    return
}
$pyw = Join-Path (Split-Path -Parent (Get-Command python).Source) "pythonw.exe"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
# 异常退出后每分钟重启，不限运行时长
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
foreach ($t in $tasks) {
    $action = New-ScheduledTaskAction -Execute $pyw -Argument $t.Args -WorkingDirectory $dir
    Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName $t.Name
    Write-Output "[服务] 已注册并启动 $($t.Name)"
}
