<#
Mute the Windows audio sessions of a process (Core Audio, per-app mute + volume 0 in the Volume Mixer).
Windows remembers a program's mixer level, so muting the editor once also keeps later launches quiet;
the bench calls this on every engine start anyway (roadcraft.audio_mute).

  powershell -NoProfile -ExecutionPolicy Bypass -File mute_audio.ps1 -Name "Roadcraft ModEditor" [-Pids 1,2] [-WaitSeconds 90]

Polls every second until a session of the process exists on any active output device (a process opens its
session only when its audio starts), mutes it, keeps watching for new sessions until WaitSeconds, prints one
line per muted session and exits 0 (1 if nothing was found).
#>
param([string]$Name = "Roadcraft ModEditor", [int[]]$Pids = @(), [int]$WaitSeconds = 90)

Add-Type -Language CSharp -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace RoadcraftAudio {
  [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumerator {}

  [Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDeviceEnumerator {
    int EnumAudioEndpoints(int dataFlow, int stateMask, out IMMDeviceCollection devices);
    int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice device);
  }
  [Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDeviceCollection {
    int GetCount(out uint count);
    int Item(uint index, out IMMDevice device);
  }
  [Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDevice {
    int Activate(ref Guid iid, int clsCtx, IntPtr activationParams, [MarshalAs(UnmanagedType.IUnknown)] out object iface);
  }
  [Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IAudioSessionManager2 {
    int GetAudioSessionControl(IntPtr groupingParam, int flags, out IntPtr control);
    int GetSimpleAudioVolume(IntPtr groupingParam, int flags, out IntPtr volume);
    int GetSessionEnumerator(out IAudioSessionEnumerator sessions);
  }
  [Guid("E2F5BB11-0570-40CA-ACDD-3AA01277DEE8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IAudioSessionEnumerator {
    int GetCount(out int count);
    int GetSession(int index, out IAudioSessionControl2 session);
  }
  [Guid("bfb7ff88-7239-4fc9-8fa2-07c950be9c6d"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IAudioSessionControl2 {
    int GetState(out int state);
    int GetDisplayName(out IntPtr name);
    int SetDisplayName(string name, ref Guid context);
    int GetIconPath(out IntPtr path);
    int SetIconPath(string path, ref Guid context);
    int GetGroupingParam(out Guid param);
    int SetGroupingParam(ref Guid param, ref Guid context);
    int RegisterAudioSessionNotification(IntPtr client);
    int UnregisterAudioSessionNotification(IntPtr client);
    int GetSessionIdentifier(out IntPtr id);
    int GetSessionInstanceIdentifier(out IntPtr id);
    int GetProcessId(out uint pid);
  }
  [Guid("87CE5498-68D6-44E5-9215-6DA47EF883D8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface ISimpleAudioVolume {
    int SetMasterVolume(float level, ref Guid context);
    int GetMasterVolume(out float level);
    int SetMute(bool mute, ref Guid context);
    int GetMute(out bool mute);
  }

  public static class Muter {
    // Mute every session on every active render device whose process id is in pids; returns "pid device" lines.
    public static List<string> Mute(HashSet<uint> pids) {
      var done = new List<string>();
      var enumerator = (IMMDeviceEnumerator)(new MMDeviceEnumerator());
      IMMDeviceCollection devices;
      enumerator.EnumAudioEndpoints(0 /*eRender*/, 1 /*ACTIVE*/, out devices);
      uint count; devices.GetCount(out count);
      Guid iid = typeof(IAudioSessionManager2).GUID, ctx = Guid.Empty;
      for (uint d = 0; d < count; d++) {
        IMMDevice device; devices.Item(d, out device);
        object o; device.Activate(ref iid, 23 /*CLSCTX_ALL*/, IntPtr.Zero, out o);
        var manager = (IAudioSessionManager2)o;
        IAudioSessionEnumerator sessions; manager.GetSessionEnumerator(out sessions);
        int n; sessions.GetCount(out n);
        for (int i = 0; i < n; i++) {
          IAudioSessionControl2 s; sessions.GetSession(i, out s);
          uint pid; s.GetProcessId(out pid);
          if (!pids.Contains(pid)) continue;
          var v = (ISimpleAudioVolume)s;
          bool muted; v.GetMute(out muted);
          if (muted) continue;
          v.SetMute(true, ref ctx);
          v.SetMasterVolume(0f, ref ctx);
          done.Add(pid + " device" + d);
        }
      }
      return done;
    }
  }
}
"@

$deadline = (Get-Date).AddSeconds($WaitSeconds)
$found = 0
do {
    $ids = New-Object 'System.Collections.Generic.HashSet[uint32]'
    foreach ($p in $Pids) { [void]$ids.Add([uint32]$p) }
    if ($Name) { Get-Process -Name $Name -ErrorAction SilentlyContinue | ForEach-Object { [void]$ids.Add([uint32]$_.Id) } }
    if ($ids.Count -gt 0) {
        foreach ($line in [RoadcraftAudio.Muter]::Mute($ids)) { Write-Output "muted $line"; $found++ }
    }
    if ((Get-Date) -ge $deadline) { break }
    Start-Sleep -Seconds 1
} while ($true)
if ($found -gt 0) { exit 0 } else { exit 1 }
