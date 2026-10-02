<#
Bounded truck-input writer for hands-off driving tests, through the native Automation/ExecSsl receiver.
Kept separate from the read-only physics probe. Only fixed statements with validated numbers:
requested pedal/steer (-1..1), optional handbrake, engine start and low range, or the view
controller's editor debug override. No arbitrary script, no keystrokes, no window focus,
no screenshots.

Unverified live (confirm once in an approved run before relying on results):
 - whether player input rewrites State requests every frame (if so, use -Method Debug);
 - whether [debug] DbgUpdateInputs runs in the ModEditor build and whether the [editor]
   dbg* fields are writable from an exec statement.

  pwsh -NoProfile -File tools/native_ssl_input_override.ps1 -Mode ValidatePayload
  pwsh -NoProfile -File tools/native_ssl_input_override.ps1 -Mode Apply -EngineProcessId 1234 `
       -OutputPath D:/abs/new/input_01.json -Pedal 1 -Steer -1 -Handbrake Off -StartEngine -LowRange
  pwsh -NoProfile -File tools/native_ssl_input_override.ps1 -Mode Release -EngineProcessId 1234 -OutputPath D:/abs/new/input_02.json
#>
[CmdletBinding()]
param(
 [ValidateSet('Apply','Release','ValidatePayload')][string]$Mode='ValidatePayload',
 [ValidateSet('State','Debug')][string]$Method='State',
 [ValidateRange(-1.0,1.0)][double]$Pedal=0,
 [ValidateRange(-1.0,1.0)][double]$Steer=0,
 [ValidateSet('Unchanged','On','Off')][string]$Handbrake='Unchanged',
 [switch]$StartEngine,
 [switch]$LowRange,
 [ValidateSet('','AUTO','LOW_GEAR','HIGH_GEAR','REVERSE','NEUTRAL')][string]$GearState='',   # GearState enum (game.truck.gearbox.truck_gearbox_state); -LowRange is LOW_GEAR; REVERSE for the reverse-lens case
 [ValidateSet('Unchanged','On','Off')][string]$Awd='Unchanged',        # gearbox state isAwdOn (CONTROLLED trucks start with AWD off)
 [ValidateSet('Unchanged','On','Off')][string]$DiffLock='Unchanged',   # gearbox state isDifflockOn
 [int]$EngineProcessId,
 [string]$OutputPath,
 [ValidateRange(1,30)][int]$TimeoutSeconds=12,
 [Parameter(Mandatory=$true)][string]$SdkEditorDirectory   # <SDK root>/tools/bin/ModEditor (Saber.ConsoleTre.dll)
)
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -lt 7){throw 'Run with pwsh 7: this helper loads .NET 6 SDK assemblies.'}
foreach($dll in @('Saber.Json.dll','Saber.ConsoleTre.dll')){
 [void][Reflection.Assembly]::LoadFrom((Join-Path $SdkEditorDirectory $dll))
}
Add-Type -IgnoreWarnings -WarningAction SilentlyContinue -ReferencedAssemblies (Join-Path $SdkEditorDirectory 'Saber.ConsoleTre.dll'),'System.Collections.Concurrent' -TypeDefinition @'
using System;
using System.IO;
using System.Collections.Concurrent;
using Saber.ConsoleTre;
public sealed class RoamerInputReplies {
 public ConcurrentQueue<byte[]> Pending = new ConcurrentQueue<byte[]>();
 public void Receive(ConsoleListener listener, UserMessage message) {
   var stream = message.GetReadStream();
   Pending.Enqueue(new NativeReader(stream, true).ReadBytes((int)stream.Length));
 }
}
'@
function Get-NativeGuidString([guid]$Guid) {
 $p=$Guid.ToString('D').Split('-')
 return '{'+$p[0].ToUpperInvariant()+'-'+$p[1].ToUpperInvariant()+'-'+$p[2].ToLowerInvariant()+'-'+$p[3].ToUpperInvariant()+'-'+$p[4].ToUpperInvariant()+'}'
}
function New-SslMessage([guid]$RequestId,[string]$Script) {
 $m=[Saber.ConsoleTre.UserMessage]::new();$w=$m.Write()
 $w.Write($RequestId.ToByteArray());$w.Write($Script,$false)
 return $m
}
function Format-Number([double]$Value){ return $Value.ToString('0.000',[Globalization.CultureInfo]::InvariantCulture) }

function Build-InputScript([string]$ScriptMode,[string]$ScriptMethod,[double]$P,[double]$S,[string]$HB,[bool]$Engine,[string]$Gear,[string]$AwdMode='Unchanged',[string]$DiffMode='Unchanged'){
 if($Gear -and $Gear -notin @('AUTO','LOW_GEAR','HIGH_GEAR','REVERSE','NEUTRAL')){throw "Unsupported gear state $Gear"}
 foreach($mode in $AwdMode,$DiffMode){if($mode -notin @('Unchanged','On','Off')){throw "Unsupported drivetrain switch $mode"}}
 $lines=@(
  'var truck = $globalStorage.TryGet<TruckManagerRb>()?.TryGetCurrent()',
  'if truck == null',' return "ROAMER_NO_CURRENT_TRUCK"','end',
  'var viewController = truck.owner.TryGet<PropTruckViewController>()',
  'if viewController == null',' return "ROAMER_NO_VIEW_CONTROLLER"','end',
  'var state = viewController.GetState()',
  'if state == null',' return "ROAMER_NO_TRUCK_STATE"','end',
  'var gearbox = truck.owner.TryGet<PropTruckGearboxController>()')
 if($ScriptMode -eq 'Release'){
  if($ScriptMethod -eq 'State'){$lines+='state.pedals.Set(0.000)','state.steering.Set(0.000)'}
  else{$lines+='viewController.dbgOverrideInputs = false','viewController.dbgAccelerationOverride = 0.000','viewController.dbgSteerOverride = 0.000'}
 }else{
  if($Engine){$lines+='state.isEngineOff.Set(false)'}
  if($HB -ne 'Unchanged'){$lines+=('state.isHandbrake.Set({0})' -f $(if($HB -eq 'On'){'true'}else{'false'}))}
  # Gear/AWD/difflock live on the gearbox controller state (truck_gearbox_state.ssl:2-4).
  $gearboxLines=@()
  if($Gear){$gearboxLines+=(' gearbox.GetState().gearState.Set(GearState.{0})' -f $Gear)}
  if($AwdMode -ne 'Unchanged'){$gearboxLines+=(' gearbox.GetState().isAwdOn.Set({0})' -f $(if($AwdMode -eq 'On'){'true'}else{'false'}))}
  if($DiffMode -ne 'Unchanged'){$gearboxLines+=(' gearbox.GetState().isDifflockOn.Set({0})' -f $(if($DiffMode -eq 'On'){'true'}else{'false'}))}
  if($gearboxLines){$lines+='if gearbox != null and gearbox.GetState() != null';$lines+=$gearboxLines;$lines+='end'}
  if($ScriptMethod -eq 'State'){$lines+=('state.pedals.Set({0})' -f (Format-Number $P)),('state.steering.Set({0})' -f (Format-Number $S))}
  else{$lines+='viewController.dbgOverrideInputs = true',('viewController.dbgAccelerationOverride = {0}' -f (Format-Number $P)),('viewController.dbgSteerOverride = {0}' -f (Format-Number $S))}
 }
 $lines+=@(
  'var result = "ROAMER_INPUT_APPLIED\n"',
  'result += StringFormat("requestedPedals %.3f\n", state.pedals.Get())',
  'result += StringFormat("requestedSteer %.3f\n", state.steering.Get())',
  'result += StringFormat("inputPedals %.3f\n", truck.input.pedals)',
  'result += StringFormat("inputSteer %.3f\n", truck.input.steer)',
  'result += "handbrake " + BoolToString(state.isHandbrake.Get(), "true", "false") + "\n"',
  'result += "handbrakeLocked " + BoolToString(state.handbrakeIsLocked.Get(), "true", "false") + "\n"',
  'result += "lowRange " + BoolToString(truck.input.isLowRangeMode, "true", "false") + "\n"',
  'result += "awdInput " + BoolToString(truck.input.isAllWheelDrive, "true", "false") + "\n"',
  'result += "difflockInput " + BoolToString(truck.input.isDiffLock, "true", "false") + "\n"',
  'if gearbox != null and gearbox.GetState() != null',
  ' result += "awdOn " + BoolToString(gearbox.GetState().isAwdOn.Get(), "true", "false") + "\n"',
  ' result += "difflockOn " + BoolToString(gearbox.GetState().isDifflockOn.Get(), "true", "false") + "\n"',
  'end')
 if($ScriptMethod -eq 'Debug'){$lines+='result += "debugOverride " + BoolToString(viewController.dbgOverrideInputs, "true", "false") + "\n"'}
 $lines+='return result'
 return ($lines -join "`n")
}

if($Mode -eq 'ValidatePayload'){
 $variants=[ordered]@{
  applyState=(Build-InputScript 'Apply' 'State' 1 -1 'Off' $true 'LOW_GEAR')
  applyDebug=(Build-InputScript 'Apply' 'Debug' -0.5 0.25 'Unchanged' $false '')
  applyHigh=(Build-InputScript 'Apply' 'State' 0 0 'Off' $true 'HIGH_GEAR')
  applyDrivetrain=(Build-InputScript 'Apply' 'Debug' 1 0 'Off' $false '' 'On' 'Off')
  releaseState=(Build-InputScript 'Release' 'State' 0 0 'Unchanged' $false '')
  releaseDebug=(Build-InputScript 'Release' 'Debug' 0 0 'Unchanged' $false '')
 }
 $g=[guid]'12abcdef-abcd-4abc-8abc-abcdef123456'
 $checks=@()
 foreach($name in $variants.Keys){
  $script=$variants[$name]
  $m=New-SslMessage $g $script;$r=$m.Read()
  $actual=[guid]::new($r.ReadBytes(16));$actualScript=$r.ReadString()
  if($actual -ne $g -or $actualScript -cne $script){throw "SDK round trip failed for $name"}
  if($script -match '[^\x20-\x7E\n]'){throw "Non-ASCII payload in $name"}
  $checks+=[ordered]@{variant=$name;bytes=[Text.Encoding]::UTF8.GetByteCount($script);sha256=[BitConverter]::ToString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($script))).Replace('-','').ToLowerInvariant()}
 }
 if($variants.applyState -notmatch 'state\.pedals\.Set\(1\.000\)' -or $variants.applyState -notmatch 'state\.steering\.Set\(-1\.000\)'){throw 'Invariant number formatting check failed'}
 if($variants.applyState -notmatch 'GearState\.LOW_GEAR' -or $variants.applyState -notmatch 'isHandbrake\.Set\(false\)'){throw 'Optional state statements missing'}
 if($variants.applyHigh -notmatch 'GearState\.HIGH_GEAR' -or $variants.applyDebug -match 'GearState'){throw 'Gear state statement check failed'}
 if($variants.applyDrivetrain -notmatch 'isAwdOn\.Set\(true\)' -or $variants.applyDrivetrain -notmatch 'isDifflockOn\.Set\(false\)' -or $variants.applyDrivetrain -notmatch 'isHandbrake\.Set\(false\)' -or $variants.applyDebug -match 'isAwdOn\.Set'){throw 'Drivetrain switch statement check failed'}
 if($variants.releaseState -match 'dbg' -or $variants.applyState -match 'dbg'){throw 'State method must not touch debug fields'}
 if((Get-NativeGuidString $g) -cne '{12ABCDEF-ABCD-4abc-8ABC-ABCDEF123456}'){throw 'Native GUID text format mismatch'}
 [ordered]@{status='pass';connected=$false;checks=$checks}|ConvertTo-Json -Depth 4
 return
}

if($LowRange -and $GearState -and $GearState -ne 'LOW_GEAR'){throw '-LowRange conflicts with -GearState'}
$script=Build-InputScript $Mode $Method $Pedal $Steer $Handbrake $StartEngine.IsPresent $(if($LowRange){'LOW_GEAR'}else{$GearState}) $Awd $DiffLock
if($EngineProcessId -le 0 -or (Get-Process -Id $EngineProcessId).ProcessName -cne 'Roadcraft ModEditor'){throw 'Exact existing native engine PID required'}
if(!$OutputPath -or ![IO.Path]::IsPathFullyQualified($OutputPath)){throw 'Absolute new output report required'}
$OutputPath=[IO.Path]::GetFullPath($OutputPath)
if(Test-Path -LiteralPath $OutputPath){throw 'Refusing to overwrite existing evidence'}
if(!(Test-Path -LiteralPath (Split-Path -Parent $OutputPath) -PathType Container)){throw 'Output directory must already exist'}
$requestId=[guid]::NewGuid();$nativeGuid=Get-NativeGuidString $requestId
$report=[ordered]@{schema=1;mode=$Mode;method=$Method;pedal=$Pedal;steer=$Steer;handbrake=$Handbrake;startEngine=$StartEngine.IsPresent;lowRange=$LowRange.IsPresent
 engineProcessId=$EngineProcessId;utc=[DateTime]::UtcNow.ToString('o');requestId=$nativeGuid;script=$script;readOnly=$false;stage='connecting'}
$report.helperSha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
function Save-Report {
 $tmp=$OutputPath+'.'+$PID+'.pending'
 $report|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $tmp -Encoding utf8NoBOM
 for($reportRetry=0; ; $reportRetry++) {
  try { [IO.File]::Move($tmp,$OutputPath,$true); break }
  catch {
   $reportError=$_.Exception
   while($reportError.InnerException){$reportError=$reportError.InnerException}
   if(($reportError.HResult -band 0xffff) -notin @(5,32,33) -or $reportRetry -ge 7){throw}
   Start-Sleep -Milliseconds ([Math]::Min(500,50*[Math]::Pow(2,$reportRetry)))
  }
 }
}
$client=$null;$speaker=$null;$listener=$null
try{
 Save-Report
 $probe=[Net.Sockets.TcpClient]::new()
 try{if(!$probe.ConnectAsync('127.0.0.1',20563).Wait([TimeSpan]::FromSeconds(3)) -or !$probe.Connected){throw 'No existing local ConsoleTre server'}}finally{$probe.Dispose()}
 $client=[Saber.ConsoleTre.ConsoleClient]::new('Roamer bounded input override','127.0.0.1','Roamer bounded input override',[long]0,20563)
 $client.StartAsync()
 if(!$client.WaitForRegistered([TimeSpan]::FromSeconds($TimeoutSeconds))){throw 'Registration timed out'}
 $list=$client.RequestClientsList();if(!$list.Wait([TimeSpan]::FromSeconds($TimeoutSeconds))){throw 'Discovery timed out'}
 $clients=$list.Result.Parse();$target=@($clients.Values|Where-Object {$_.ProcessId -eq $EngineProcessId})
 if($target.Count -ne 1){throw 'Native engine PID does not identify one client'}
 $target=$target[0]
 $inbound=@($target.Listeners|Where-Object {$_.Passport.Contains('Module','Automation') -and $_.Passport.Contains('Type','ExecSsl')})
 if($inbound.Count -ne 1){throw 'Exact native engine has no unique Automation/ExecSsl listener'}
 $workspace=@($inbound[0].Passport|Where-Object {$_.Name -eq 'Workspace' -and !$_.ShouldAbsent})
 if($workspace.Count -ne 1 -or !$workspace[0].Value){throw 'Missing native workspace identity'}
 $matches=@($clients.Values|Where-Object {$_.ChannelIndex -eq $target.ChannelIndex}|ForEach-Object {$_.Listeners}|Where-Object {$_.Passport.Contains('Module','Automation') -and $_.Passport.Contains('Type','ExecSsl') -and $_.Passport.Contains('Workspace',$workspace[0].Value)})
 if($matches.Count -ne 1){throw 'Ambiguous native SSL destination; refusing broadcast'}
 $client.ChangeChannel([int]$target.ChannelIndex)
 $sp=[Saber.ConsoleTre.SpeakerPassport]::new($false)
 foreach($c in $inbound[0].Passport){if(!$c.ShouldAbsent){$sp.Add($c.Name,$c.Value)}}
 $lp=[Saber.ConsoleTre.ListenerPassport]::new($false);$lp.Add('__PrivateId__',$nativeGuid)
 $queue=[RoamerInputReplies]::new();$listener=$client.CreateListener($lp);$listener.add_ReceiveMessage($queue.Receive)
 $speaker=$client.CreateSpeaker($sp)
 $deadline=[DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
 while((!$speaker.HasConnectedListeners -or !$listener.IsRegistered) -and [DateTime]::UtcNow -lt $deadline){Start-Sleep -Milliseconds 40}
 if(!$speaker.HasConnectedListeners -or !$listener.IsRegistered){throw 'Exact native SSL transport did not connect'}
 $report.workspace=$workspace[0].Value;$report.stage='connected';Save-Report
 if(!$speaker.Send((New-SslMessage $requestId $script))){throw 'Transport rejected request'}
 $report.requestSentUtc=[DateTime]::UtcNow.ToString('o');$report.stage='request_sent';Save-Report
 $deadline=[DateTime]::UtcNow.AddSeconds($TimeoutSeconds);$raw=$null
 while(!$queue.Pending.TryDequeue([ref]$raw) -and [DateTime]::UtcNow -lt $deadline){Start-Sleep -Milliseconds 40}
 if($null -eq $raw){throw 'No correlated native SSL response received (statement may not compile in this build)'}
 if($raw.Length -lt 1 -or $raw[$raw.Length-1] -ne 0 -or [Array]::IndexOf($raw,[byte]0) -ne $raw.Length-1){throw 'Unexpected native reply framing'}
 $report.response=[Text.UTF8Encoding]::new($false,$true).GetString($raw,0,$raw.Length-1)
 $report.receivedUtc=[DateTime]::UtcNow.ToString('o');$report.stage='response_received'
 if($report.response -notmatch '^ROAMER_INPUT_APPLIED\n'){throw ('Native did not confirm input: '+$report.response)}
 $report.status='pass';Save-Report
 [ordered]@{status='pass';mode=$Mode;method=$Method;output=$OutputPath;response=$report.response}|ConvertTo-Json
}catch{
 $report.status='failed';$report.error=$_.Exception.Message;Save-Report;throw
}finally{
 if($client){if($speaker){$client.DestroySpeaker($speaker)};if($listener){$client.DestroyListener($listener)};$client.Close()}
}
