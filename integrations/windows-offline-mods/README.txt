RoadCraft Offline Mods

1. Close RoadCraft.
2. Copy your mod's .pak into RoadCraft\root\mods.
3. Open RoadCraftOfflineMods.exe, select your mod and click Enable.
4. Start RoadCraft.

Check the game folder if your mod isn't listed. If you have more than one
profile, select the profile you actually use.

Disable turns off the selected mod. Restore backup restores an earlier
user_settings.cfg. Every change saves the previous file beside it as
user_settings.cfg.offline-mods-DATE-ID.bak.

This edits the local enabledMods setting. It does not download mods or fix
the online browser. The tool uses Windows' built-in .NET Framework 4.5+;
Python is not needed. No administrator rights are normally needed.

Tested against copies of current retail settings, including decoding,
encoding, enabling, disabling, preserving other settings and restoring
backups. Actual in-game activation has not yet been tested. Future game
updates may change the format. Unsupported or corrupt files are refused.

Source: OfflineMods.cs. Build using Windows' Framework64 csc.exe, targeting
winexe with references to System.Windows.Forms.dll, System.Drawing.dll
and System.Web.Extensions.dll. The application has no network functions.
