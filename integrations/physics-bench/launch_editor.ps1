<#
Start the Mod Editor (IntegrationStudio) on a physics-bench project with its play scenario, window
hidden; dismiss the "send errors from past sessions" prompt with Later (nothing is sent); wait for the
scenario's ready marker; report the studio and native engine PIDs in RunDir/launch.json.

Refuses when another editor or the game runs. Launching the editor uses the PC: get the owner's
go-ahead first (library/physics-bench.md). Used by roadcraft.physics_bench.
#>
[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][string]$RunDir,
 [Parameter(Mandatory=$true)][string]$Project,
 [Parameter(Mandatory=$true)][string]$DataDir,
 [Parameter(Mandatory=$true)][string]$ProfilesDir,
 [Parameter(Mandatory=$true)][string]$Scenario,
 [Parameter(Mandatory=$true)][string]$Editor,
 [string]$Profile='map_editor_next',
 [string]$ReadyMarker='BENCH_GAME_MODE_READY',
 [int]$ReadyTimeoutSeconds=600
)
$ErrorActionPreference='Stop'
if (Get-Process IntegrationStudio -ErrorAction SilentlyContinue) { throw 'An editor is already running; not starting another.' }
if (Get-Process | Where-Object { $_.ProcessName -match 'roadcraft' }) { throw 'RoadCraft or its editor is running.' }
New-Item -ItemType Directory -Path $RunDir -Force | Out-Null
$editorArgs=@('--project',('"'+$Project+'"'),'--create-local-project','false','--data-dir',('"'+$DataDir+'"'),
              '--local-profiles-dir',('"'+$ProfilesDir+'"'),'--profile',$Profile,'--automation','--scenario',('"'+$Scenario+'"'))
$proc=Start-Process -FilePath $Editor -ArgumentList $editorArgs -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput (Join-Path $RunDir 'stdout.log') -RedirectStandardError (Join-Path $RunDir 'stderr.log')
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$deadline=(Get-Date).AddSeconds($ReadyTimeoutSeconds)
$ready=$false
while((Get-Date) -lt $deadline -and -not $proc.HasExited){
 Start-Sleep -Seconds 2
 $proc.Refresh()
 if ($proc.MainWindowTitle -eq 'Integration Studio: Crash Reporter') {
  $w=[System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
  $q=[System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::NameProperty,'Send errors from past sessions?')
  if ($w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$q)) {
   $b=$w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::NameProperty,'Later'))
   $b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
   Write-Output 'Dismissed historical crash-report prompt (Later, nothing sent).'
  }
 }
 $log=Get-Content -LiteralPath (Join-Path $RunDir 'stdout.log') -Raw -ErrorAction SilentlyContinue
 if ($log -match [regex]::Escape($ReadyMarker)) { $ready=$true; break }
}
$engine=Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $proc.Id -and $_.Name -eq 'Roadcraft ModEditor.exe' } | Select-Object -First 1
$proc.Refresh()
$info=@{studioPid=$proc.Id; enginePid=$(if($engine){[int]$engine.ProcessId}else{$null}); ready=($ready -and -not $proc.HasExited -and $engine); exited=$proc.HasExited; at=(Get-Date -Format o)}
$info | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $RunDir 'launch.json')
$info | ConvertTo-Json
if (-not $info.ready) { exit 2 }
