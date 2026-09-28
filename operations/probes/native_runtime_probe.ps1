<#
Scratch-only, read-only SSL probe transport. The default is offline preflight.
Execution requires -Execute, an exact existing editor PID, and a new receipt.
No arbitrary SSL text, fragment path, editor path, or scene path is accepted.
The scene hash pins source bytes only; it does not prove the loaded scene.
#>
[CmdletBinding()]
param(
 [Parameter(Mandatory)][ValidateSet('weather_state','camera_up','sun_direction','daytime')][string]$Kind,
 [Parameter(Mandatory)][ValidateSet('maroon','nearnew','worn')][string]$Variant,
 [int]$EngineProcessId,
 [string]$OutputPath,
 [ValidateRange(1,30)][int]$TimeoutSeconds=12,
 [switch]$Execute
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest

# Review these pins when source/editor bytes change; never learn a new hash
# from the installed executable or a generated candidate during execution.
$probePins=@{
 weather_state='c39033a632e0ec8e3f36bf6e6dda1f0602d67bdd12d6a77b364461982d43b809'
 camera_up='086a93e10c29f97bd5dd215e7a0f155c4f0588618178480105f9d1a50ad9f09b'
 sun_direction='2ebd5914d635fae2ff603e73721f0c649fd5de927a50bd7a9aad46f4a1bff6fe'
 daytime='be7b9db66ce6a1df6a8ee3e1ed597f9cf6ccebddeb7ec2797c965e7b279ddd86'
}
$scenePins=@{
 maroon='9481bca1db96dd5c3c0c201f9d7f84e0b16fd7e683905c286060b16e9d53dfa1'
 nearnew='7bb6428240ecb1acf0d31674d855d8af6eebefe57f62d7f4956bf8d603b0a701'
 worn='a518939a52afa5dd946a480161545e257fa89c7d0968d489937a27adf5a1bd8c'
}
$editorPin='ce6a48b1c73bea0876376d3251a6810b4a9913a7d500226e42bb2c605f3810b7'
$jsonDllPin='60aad8900d2e663fe8a7e3606f644bf9b4e6f482112ca2514a9b499b4c9134cc'
$consoleDllPin='26007b4d104045fc9aed7276761534abe42b07f293ca757385d47635ccd9b3f3'

function Assert-Hash([string]$Path,[string]$Expected,[string]$Label) {
 if(!(Test-Path -LiteralPath $Path -PathType Leaf)){throw "Missing $Label"}
 $actual=(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
 if($actual -cne $Expected){throw "$Label SHA-256 mismatch"}
 return $actual
}
function Get-NativeGuidString([guid]$Guid) {
 $p=$Guid.ToString('D').Split('-')
 return '{'+$p[0].ToUpperInvariant()+'-'+$p[1].ToUpperInvariant()+'-'+$p[2].ToLowerInvariant()+'-'+$p[3].ToUpperInvariant()+'-'+$p[4].ToUpperInvariant()+'}'
}
function New-SslMessage([guid]$RequestId,[string]$Script) {
 $message=[Saber.ConsoleTre.UserMessage]::new()
 $writer=$message.Write()
 $writer.Write($RequestId.ToByteArray())
 $writer.Write($Script,$false)
 return $message
}
function Assert-Engine([int]$ProcessId,[string]$ExpectedPath,[string]$ExpectedStartUtc) {
 if($ProcessId -le 0){throw 'Exact existing editor PID required'}
 $engine=Get-Process -Id $ProcessId -ErrorAction Stop
 if($engine.ProcessName -cne 'Roadcraft ModEditor'){throw 'PID is not Roadcraft ModEditor'}
 if(!$engine.Path){throw 'Editor process path could not be inspected'}
 $actualPath=[IO.Path]::GetFullPath($engine.Path)
 if(![string]::Equals($actualPath,[IO.Path]::GetFullPath($ExpectedPath),[StringComparison]::OrdinalIgnoreCase)){
  throw 'PID executable path does not match pinned editor'
 }
 $start=$engine.StartTime.ToUniversalTime().ToString('o')
 if($ExpectedStartUtc -and $start -cne $ExpectedStartUtc){throw 'Editor PID was recycled during probe'}
 return $start
}
function Save-Receipt([hashtable]$Receipt,[string]$Path) {
 $json=$Receipt|ConvertTo-Json -Depth 16
 $bytes=[Text.UTF8Encoding]::new($false).GetBytes($json+"`n")
 $stream=[IO.File]::Open($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
 try { $stream.Write($bytes,0,$bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
}
function Assert-PlainDirectoryTree([string]$Directory) {
 $current=[IO.Path]::GetFullPath($Directory)
 while($true){
  $item=Get-Item -LiteralPath $current -Force -ErrorAction Stop
  if(!$item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)){
   throw 'Scratch output has a non-directory or reparse-point ancestor'
  }
  $parent=[IO.Directory]::GetParent($current)
  if($null -eq $parent){break}
  $current=$parent.FullName
 }
}

$toolchainRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$machineConfigPath=if($env:ROADCRAFT_CONFIG){$env:ROADCRAFT_CONFIG}else{Join-Path $toolchainRoot 'local\machine.json'}
if(!(Test-Path -LiteralPath $machineConfigPath -PathType Leaf)){throw 'Missing machine configuration'}
$machineConfigPath=[IO.Path]::GetFullPath($machineConfigPath)
$machineConfigSha=(Get-FileHash -LiteralPath $machineConfigPath -Algorithm SHA256).Hash.ToLowerInvariant()
$machineConfig=Get-Content -LiteralPath $machineConfigPath -Raw -Encoding utf8|ConvertFrom-Json
if(!$machineConfig.sdkRoot -or ![IO.Path]::IsPathFullyQualified($machineConfig.sdkRoot)){throw 'Machine SDK root is not absolute'}
$workspaceRoot=[IO.Path]::GetFullPath($machineConfig.sdkRoot)
$gameRoot=Split-Path -Parent $workspaceRoot
$editorPath=Join-Path $gameRoot 'root\bin\pc\Roadcraft ModEditor.exe'
$sdkEditorDirectory=Join-Path $gameRoot 'tools\bin\ModEditor'
$jsonDllPath=Join-Path $sdkEditorDirectory 'Saber.Json.dll'
$consoleDllPath=Join-Path $sdkEditorDirectory 'Saber.ConsoleTre.dll'
$sceneName="d11t_${Variant}_validation"
$scenePath=Join-Path $workspaceRoot "D11_Interior_AAA_20260928\p\mods_source\xscenes\mods\$sceneName\$sceneName.scn"
$fragmentPath=Join-Path $PSScriptRoot "d11_${Kind}.ssl"
$fragmentSha=Assert-Hash $fragmentPath $probePins[$Kind] 'probe fragment'
$sceneSha=Assert-Hash $scenePath $scenePins[$Variant] 'validation scene source'
$editorSha=Assert-Hash $editorPath $editorPin 'native editor executable'
$jsonDllSha=Assert-Hash $jsonDllPath $jsonDllPin 'Saber.Json.dll'
$consoleDllSha=Assert-Hash $consoleDllPath $consoleDllPin 'Saber.ConsoleTre.dll'
$helperSha=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
$strictUtf8=[Text.UTF8Encoding]::new($false,$true)
$fragmentBytes=[IO.File]::ReadAllBytes($fragmentPath)
$scriptSha=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($fragmentBytes)).ToLowerInvariant()
if($scriptSha -cne $probePins[$Kind]){throw 'Exact in-memory probe bytes SHA-256 mismatch'}
$script=$strictUtf8.GetString($fragmentBytes)
if(!$script.Trim()){throw 'Probe fragment is empty'}

$plan=@{
 schema=1; status='PREFLIGHT_ONLY'; readOnly=$true; pairProtocolEligible=$false
 probeKind=$Kind; variant=$Variant; fragmentPath=$fragmentPath; fragmentSha256=$fragmentSha
 sceneSourcePath=$scenePath; sceneSourceSha256=$sceneSha; loadedSceneVerified=$false
 editorPath=$editorPath; editorSha256=$editorSha; helperPath=$PSCommandPath; helperSha256=$helperSha
 jsonDllPath=$jsonDllPath; jsonDllSha256=$jsonDllSha
 consoleDllPath=$consoleDllPath; consoleDllSha256=$consoleDllSha
 machineConfigPath=$machineConfigPath; machineConfigSha256=$machineConfigSha
 requestScript=$script; requestScriptSha256=$scriptSha; transportSent=$false
}
if(!$Execute){$plan|ConvertTo-Json -Depth 8;return}

if(!$OutputPath -or ![IO.Path]::IsPathFullyQualified($OutputPath)){throw 'Absolute new JSON output path required'}
$OutputPath=[IO.Path]::GetFullPath($OutputPath)
if([IO.Path]::GetExtension($OutputPath) -cne '.json'){throw 'Output must be a JSON receipt'}
$scratchRoot=[IO.Path]::GetFullPath((Join-Path $toolchainRoot 'local\native-probes'))
if(![string]::Equals((Split-Path -Parent $OutputPath),$scratchRoot,[StringComparison]::OrdinalIgnoreCase)){
 throw 'Receipt must be a direct child of toolchain local/native-probes'
}
if([IO.Path]::GetFileName($OutputPath) -cnotmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.json$'){
 throw 'Receipt filename is not a plain JSON basename'
}
Assert-PlainDirectoryTree (Join-Path $toolchainRoot 'local')
if(!(Test-Path -LiteralPath $scratchRoot)){[void](New-Item -ItemType Directory -Path $scratchRoot)}
Assert-PlainDirectoryTree $scratchRoot
if($null -ne (Get-Item -LiteralPath $OutputPath -Force -ErrorAction SilentlyContinue)){
 throw 'Refusing to overwrite or follow existing evidence'
}
$startUtc=Assert-Engine $EngineProcessId $editorPath ''
$requestId=[guid]::NewGuid()
$nativeGuid=Get-NativeGuidString $requestId
$receipt=$plan.Clone()
$receipt.status='FAILED'
$receipt.stage='pre_send'
$receipt.engineProcessId=$EngineProcessId
$receipt.engineStartUtc=$startUtc
$receipt.requestId=$nativeGuid
$receipt.requestPreparedUtc=[DateTime]::UtcNow.ToString('o')
$client=$null;$speaker=$null;$listener=$null
try {
 [void][Reflection.Assembly]::LoadFrom($jsonDllPath)
 [void][Reflection.Assembly]::LoadFrom($consoleDllPath)
 Add-Type -IgnoreWarnings -WarningAction SilentlyContinue -ReferencedAssemblies (Join-Path $sdkEditorDirectory 'Saber.ConsoleTre.dll'),'System.Collections.Concurrent' -TypeDefinition @'
using System;
using System.Collections.Concurrent;
using Saber.ConsoleTre;
public sealed class D11RuntimeProbeReplies {
 public const int MaxReplyBytes = 65536;
 public ConcurrentQueue<byte[]> Pending = new ConcurrentQueue<byte[]>();
 public ConcurrentQueue<string> Failures = new ConcurrentQueue<string>();
 public void Receive(ConsoleListener listener, UserMessage message) {
   try {
     var stream = message.GetReadStream();
     if (stream.Length < 1 || stream.Length > MaxReplyBytes) {
       Failures.Enqueue("Native reply length outside 1..65536 bytes");
       return;
     }
     Pending.Enqueue(new NativeReader(stream, true).ReadBytes((int)stream.Length));
   } catch (Exception) {
     Failures.Enqueue("Native reply could not be read");
   }
 }
}
'@
 $socket=[Net.Sockets.TcpClient]::new()
 try {
  if(!$socket.ConnectAsync('127.0.0.1',20563).Wait([TimeSpan]::FromSeconds(3)) -or !$socket.Connected){
   throw 'No existing local ConsoleTre server'
  }
 } finally { $socket.Dispose() }
 $client=[Saber.ConsoleTre.ConsoleClient]::new('D11 scratch runtime readback','127.0.0.1','D11 scratch runtime readback',[long]0,20563)
 $client.StartAsync()
 if(!$client.WaitForRegistered([TimeSpan]::FromSeconds($TimeoutSeconds))){throw 'Registration timed out'}
 $list=$client.RequestClientsList()
 if(!$list.Wait([TimeSpan]::FromSeconds($TimeoutSeconds))){throw 'Discovery timed out'}
 $clients=$list.Result.Parse()
 $targets=@($clients.Values|Where-Object {$_.ProcessId -eq $EngineProcessId})
 if($targets.Count -ne 1){throw 'Editor PID does not identify one ConsoleTre client'}
 $target=$targets[0]
 $inbound=@($target.Listeners|Where-Object {$_.Passport.Contains('Module','Automation') -and $_.Passport.Contains('Type','ExecSsl')})
 if($inbound.Count -ne 1){throw 'Editor PID has no unique Automation/ExecSsl listener'}
 $workspace=@($inbound[0].Passport|Where-Object {$_.Name -eq 'Workspace' -and !$_.ShouldAbsent})
 if($workspace.Count -ne 1 -or !$workspace[0].Value){throw 'Missing native workspace identity'}
 $matches=@($clients.Values|Where-Object {$_.ChannelIndex -eq $target.ChannelIndex}|ForEach-Object {$_.Listeners}|Where-Object {$_.Passport.Contains('Module','Automation') -and $_.Passport.Contains('Type','ExecSsl') -and $_.Passport.Contains('Workspace',$workspace[0].Value)})
 if($matches.Count -ne 1){throw 'Ambiguous native SSL destination'}
 $client.ChangeChannel([int]$target.ChannelIndex)
 $speakerPassport=[Saber.ConsoleTre.SpeakerPassport]::new($false)
 foreach($component in $inbound[0].Passport){if(!$component.ShouldAbsent){$speakerPassport.Add($component.Name,$component.Value)}}
 $replyPassport=[Saber.ConsoleTre.ListenerPassport]::new($false)
 $replyPassport.Add('__PrivateId__',$nativeGuid)
 $queue=[D11RuntimeProbeReplies]::new()
 $listener=$client.CreateListener($replyPassport)
 $listener.add_ReceiveMessage($queue.Receive)
 $speaker=$client.CreateSpeaker($speakerPassport)
 $deadline=[DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
 while((!$speaker.HasConnectedListeners -or !$listener.IsRegistered) -and [DateTime]::UtcNow -lt $deadline){Start-Sleep -Milliseconds 40}
 if(!$speaker.HasConnectedListeners -or !$listener.IsRegistered){throw 'Exact native SSL transport did not connect'}
 $receipt.workspace=$workspace[0].Value
 [void](Assert-Engine $EngineProcessId $editorPath $startUtc)
 [void](Assert-Hash $fragmentPath $fragmentSha 'probe fragment at send')
 $sendBytes=$strictUtf8.GetBytes($script)
 $sendSha=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($sendBytes)).ToLowerInvariant()
 if($sendSha -cne $probePins[$Kind]){throw 'SSL script bytes changed before send'}
 [void](Assert-Hash $PSCommandPath $helperSha 'scratch helper at send')
 [void](Assert-Hash $machineConfigPath $machineConfigSha 'machine configuration at send')
 [void](Assert-Hash $scenePath $sceneSha 'validation scene source at send')
 [void](Assert-Hash $editorPath $editorSha 'native editor executable at send')
 [void](Assert-Hash $jsonDllPath $jsonDllSha 'Saber.Json.dll at send')
 [void](Assert-Hash $consoleDllPath $consoleDllSha 'Saber.ConsoleTre.dll at send')
 $receipt.requestSendStartedUtc=[DateTime]::UtcNow.ToString('o')
 $receipt.stage='sending'
 if(!$speaker.Send((New-SslMessage $requestId $script))){throw 'Transport rejected request'}
 $receipt.requestSentUtc=[DateTime]::UtcNow.ToString('o')
 $receipt.transportSent=$true
 $receipt.stage='request_sent'
 $deadline=[DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
 $raw=$null
 $receiveFailure=$null
 while([DateTime]::UtcNow -lt $deadline){
  if($queue.Failures.TryDequeue([ref]$receiveFailure)){throw $receiveFailure}
  if($queue.Pending.TryDequeue([ref]$raw)){break}
  Start-Sleep -Milliseconds 40
 }
 if($queue.Failures.TryDequeue([ref]$receiveFailure)){throw $receiveFailure}
 if($null -eq $raw){throw 'No correlated native SSL response received'}
 $receipt.responseReceivedUtc=[DateTime]::UtcNow.ToString('o')
 $receipt.responseBytes=$raw.Length
 $receipt.responseBase64=[Convert]::ToBase64String($raw)
 $receipt.responseSha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($raw)).ToLowerInvariant()
 if($raw.Length -lt 1 -or $raw[$raw.Length-1] -ne 0){throw 'Native reply lacks NUL terminator'}
 if([Array]::IndexOf($raw,[byte]0) -ne $raw.Length-1){throw 'Native reply has embedded NUL'}
 $receipt.response=$strictUtf8.GetString($raw,0,$raw.Length-1)
 [void](Assert-Engine $EngineProcessId $editorPath $startUtc)
 [void](Assert-Hash $fragmentPath $fragmentSha 'probe fragment after reply')
 [void](Assert-Hash $PSCommandPath $helperSha 'scratch helper after reply')
 [void](Assert-Hash $machineConfigPath $machineConfigSha 'machine configuration after reply')
 [void](Assert-Hash $scenePath $sceneSha 'validation scene source after reply')
 [void](Assert-Hash $editorPath $editorSha 'native editor executable after reply')
 [void](Assert-Hash $jsonDllPath $jsonDllSha 'Saber.Json.dll after reply')
 [void](Assert-Hash $consoleDllPath $consoleDllSha 'Saber.ConsoleTre.dll after reply')
 $receipt.stage='response_received'
 $receipt.status='TRANSPORT_RESPONSE_UNVALIDATED'
} catch {
 $receipt.error=$_.Exception.Message
 throw
} finally {
 try {
  if($client){
   if($speaker){$client.DestroySpeaker($speaker)}
   if($listener){$client.DestroyListener($listener)}
   $client.Close()
  }
 } catch {
  $receipt.status='FAILED'
  $receipt.stage='cleanup_failed'
  $receipt.error=$_.Exception.Message
  throw
 } finally { Save-Receipt $receipt $OutputPath }
}
$receipt|ConvertTo-Json -Depth 16
