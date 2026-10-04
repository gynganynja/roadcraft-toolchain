<#
Read-only time series of the current truck's bodies and wheels through the editor's native
Automation/ExecSsl receiver (same transport as port_roamer105/tools/native_ssl_physics_probe.ps1).
One connection, one fixed read-only statement repeated Count times. Writes JSON lines.
#>
[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][int]$EngineProcessId,
 [Parameter(Mandatory=$true)][string]$OutputPath,
 [ValidateRange(1,20000)][int]$Count=600,
 [ValidateRange(0,5000)][int]$IntervalMs=80,
 [ValidateRange(0,3600)][int]$DurationSeconds=0,
 [ValidateRange(1,30)][int]$TimeoutSeconds=12,
 [Parameter(Mandatory=$true)][string]$SdkEditorDirectory   # <SDK root>/tools/bin/ModEditor (Saber.ConsoleTre.dll)
)
$ErrorActionPreference='Stop'
foreach($dll in @('Saber.Json.dll','Saber.ConsoleTre.dll')){
 [void][Reflection.Assembly]::LoadFrom((Join-Path $SdkEditorDirectory $dll))
}
Add-Type -IgnoreWarnings -WarningAction SilentlyContinue -ReferencedAssemblies (Join-Path $SdkEditorDirectory 'Saber.ConsoleTre.dll'),'System.Collections.Concurrent' -TypeDefinition @'
using System;
using System.IO;
using System.Collections.Concurrent;
using Saber.ConsoleTre;
public sealed class KgsSeriesReplies {
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
$script=@'
var truck = $globalStorage.TryGet<TruckManagerRb>()?.TryGetCurrent()
if truck == null
 return "NO_TRUCK"
end
var ps = truck.owner.Get<PropPhysSystem>().GetPhysSys()
if ps == null
 return "NO_PHYS"
end
var result = StringFormat("F %i %.4f %.3f", GetFrameNmb(), truck.GetForwardLinearVelocity(), truck.input.pedals)
result += StringFormat(" %.3f\n", truck.input.steer)
result += StringFormat("G %i %.1f", truck.GetGear(), truck.GetCurrentEngineRpm())
result += " " + BoolToString(truck.input.isHandbrake, "1", "0")
var viewController = truck.owner.TryGet<PropTruckViewController>()
if viewController != null
 result += " " + BoolToString(viewController.GetSslEngine().IsEngineRunning(), "1", "0")
 result += " " + BoolToString(viewController.GetSslEngine().IsBrakePull(), "1", "0")
end
result += "\n"
for (var i = 0; i < ps.GetBodyCount() and i < 64; i += 1)
 var body = ps.GetBodyByIdx(i)
 var t = body.transform
 var v = t.GetPosition()
 result += "B " + body.GetName()
 result += StringFormat(" %.5f %.5f %.5f", v.x, v.y, v.z)
 v = t.GetUp()
 result += StringFormat(" %.5f %.5f %.5f", v.x, v.y, v.z)
 v = t.GetForward()
 result += StringFormat(" %.5f %.5f %.5f\n", v.x, v.y, v.z)
 var cl = body.GetCenterOfMassLocal()
 var cw = body.GetCenterOfMass()
 result += "C " + body.GetName() + StringFormat(" %.3f %.5f %.5f %.5f", body.GetMass(), cl.x, cl.y, cl.z)
 result += StringFormat(" %.5f %.5f %.5f\n", cw.x, cw.y, cw.z)
end
var wheels = truck.GetWheels()
for var wheel in wheels
 result += StringFormat("W %.4f", wheel.GetCurrentSpringTravelDistance())
 var info = wheel.runtimeInfo
 if info != null
  var wp = info.transform.GetPosition()
  result += StringFormat(" %.4f %.4f %.4f", wp.x, wp.y, wp.z)
  result += " " + BoolToString(info.isOnGround, "1", "0")
  result += StringFormat(" %.3f %.4f %.4f", info.angularVelocity, info.forwardLinearVelocity, wheel.GetPhysicalRadius())
  result += StringFormat(" %.4f", info.mudDepth) + " " + BoolToString(info.isOnTerrain, "1", "0")
 end
 result += "\n"
end
return result
'@
if(!(Test-Path -LiteralPath (Split-Path -Parent $OutputPath) -PathType Container)){throw 'Output directory must already exist'}
$requestId=[guid]::NewGuid();$nativeGuid=Get-NativeGuidString $requestId
$client=$null;$speaker=$null;$listener=$null
$writer=[IO.StreamWriter]::new($OutputPath,$false,[Text.UTF8Encoding]::new($false))
try{
 $probe=[Net.Sockets.TcpClient]::new()
 try{if(!$probe.ConnectAsync('127.0.0.1',20563).Wait([TimeSpan]::FromSeconds(3)) -or !$probe.Connected){throw 'No existing local ConsoleTre server'}}finally{$probe.Dispose()}
 $client=[Saber.ConsoleTre.ConsoleClient]::new('KGS25 read-only series probe','127.0.0.1','KGS25 read-only series probe',[long]0,20563)
 $client.StartAsync()
 if(!$client.WaitForRegistered([TimeSpan]::FromSeconds($TimeoutSeconds))){throw 'Registration timed out'}
 $list=$client.RequestClientsList();if(!$list.Wait([TimeSpan]::FromSeconds($TimeoutSeconds))){throw 'Discovery timed out'}
 $clients=$list.Result.Parse();$target=@($clients.Values|Where-Object {$_.ProcessId -eq $EngineProcessId})
 if($target.Count -ne 1){throw 'Native engine PID does not identify one client'}
 $target=$target[0]
 $inbound=@($target.Listeners|Where-Object {$_.Passport.Contains('Module','Automation') -and $_.Passport.Contains('Type','ExecSsl')})
 if($inbound.Count -ne 1){throw 'Exact native engine has no unique Automation/ExecSsl listener'}
 $client.ChangeChannel([int]$target.ChannelIndex)
 $sp=[Saber.ConsoleTre.SpeakerPassport]::new($false)
 foreach($c in $inbound[0].Passport){if(!$c.ShouldAbsent){$sp.Add($c.Name,$c.Value)}}
 $lp=[Saber.ConsoleTre.ListenerPassport]::new($false);$lp.Add('__PrivateId__',$nativeGuid)
 $queue=[KgsSeriesReplies]::new();$listener=$client.CreateListener($lp);$listener.add_ReceiveMessage($queue.Receive)
 $speaker=$client.CreateSpeaker($sp)
 $deadline=[DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
 while((!$speaker.HasConnectedListeners -or !$listener.IsRegistered) -and [DateTime]::UtcNow -lt $deadline){Start-Sleep -Milliseconds 40}
 if(!$speaker.HasConnectedListeners -or !$listener.IsRegistered){throw 'Exact native SSL transport did not connect'}
 $sw=[Diagnostics.Stopwatch]::StartNew()
 $failures=0
 for($i=0;$i -lt $Count;$i++){
  if($DurationSeconds -gt 0 -and $sw.Elapsed.TotalSeconds -ge $DurationSeconds){break}
  $sent=$sw.Elapsed.TotalSeconds
  if(!$speaker.Send((New-SslMessage $requestId $script))){throw 'Transport rejected request'}
  $raw=$null;$deadline=[DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
  while(!$queue.Pending.TryDequeue([ref]$raw) -and [DateTime]::UtcNow -lt $deadline){Start-Sleep -Milliseconds 5}
  if($null -eq $raw){$failures++; if($failures -gt 5){throw 'Repeated missing responses'}; continue}
  $text=[Text.UTF8Encoding]::new($false,$false).GetString($raw,0,[Math]::Max(0,$raw.Length-1))
  $writer.WriteLine((@{i=$i;t=[Math]::Round($sent,4);utc=[DateTime]::UtcNow.ToString('o');r=$text}|ConvertTo-Json -Compress))
  if(($i % 20) -eq 0){$writer.Flush()}
  if($IntervalMs -gt 0){Start-Sleep -Milliseconds $IntervalMs}
 }
 Write-Output "series done: $i samples, $failures missing"
}finally{
 $writer.Flush();$writer.Dispose()
 if($client){if($speaker){$client.DestroySpeaker($speaker)};if($listener){$client.DestroyListener($listener)};$client.Close()}
}
