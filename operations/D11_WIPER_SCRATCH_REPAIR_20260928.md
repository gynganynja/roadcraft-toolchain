# D11 wiper scratch repair, unexecuted — 2026-09-28

Read-only Blender 5.2 inspection of the pinned historical `cat_d11t.blend`
(`1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`)
found one `D11T_Rig.005` armature with `BoneAnim_WiperFront` under
`BoneChassis_cdt`, and two layered actions targeting that bone. Each action
contains exactly three Euler rotation curves with three keyframes per curve.
`d11_wipers_backward` spans frames 20–37; `d11_wipers_forward` spans 1–18.
Each has the object slot `OBD11T_Rig.005`. The armature has no active action or
slot. Source Blend and repaired USF hashes were unchanged after inspection.
The read-only Blender inspection also confirmed that `bpy.data.actions`
iterates backward then forward, matching the order required by the guarded
repair; both source hashes were still unchanged after that check.

The bundled SDK's `scene.py` initializes bone animation only when the armature
has an active action. Its `misc.py` then walks every action, but `_bake_anim`
uses an end-exclusive `range`, omitting the last frame of each. This explains
why the existing native scratch export has zero animated nodes and predicts
that simply binding one action would produce 34 samples, not the repaired 36.
The reviewed SDK files are pinned by SHA-256
`386567f324799274fc7b1ab6c3c92898b19d0d04de6f072ab5b4a47001c551fd`
(`scene.py`) and
`301d79c7e98edee58da0c4e77229524291968ce504a99be07dc76e1a09358a1c`
(`misc.py`).

Read-only parsing of the pinned repaired base USF
(`49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170`)
found actor animations in backward-then-forward order, with spans 1–18 and
19–36. Its wiper translation, rotation and scale splines each contain 36
samples numbered 1–36. The selected rotation samples go from about −45°
at sample 1 to 0° at samples 18–19 and back to about −45° at sample 36,
consistent with the two source actions in that order. This is a mapping
hypothesis; the exact transform values have not been reproduced by a native
scratch export.

The SDK also copies each source action's original frame range into actor
metadata. Those ranges are backward 20–37 and forward 1–18, whereas the
repaired USF records 1–18 and 19–36. The scratch repair does not rewrite
actor metadata, so even a 36-key node result cannot establish complete
animation parity.

`blender_wiper_repair.py` adds an opt-in repair to the authoring diagnostic.
After every pin and source-shape check passes, it binds the existing forward
action to the rig in memory and replaces the SDK's bake loop with an inclusive
endpoint loop for these two actions only. It does not edit the SDK, save a
Blend, or authorize a native build source. The helper records action order,
per-action sample counts and resulting native spline key counts. The
authoring probe still compares the entire USF and calls the closed
`native-blend` export gate.

The following *dry run* passed with `status: DRY_RUN`, one Blender thread,
and zero output files. It rechecked the accepted inventory, this asset's pinned
Blend and repaired USF, plus Blender, SDK and repair-module hashes. To perform the
separately authorized scratch export, use the same command with `--run` as
shown here. The source is the pinned historical Blend and repaired USF named
above. Only the new scratch directory and receipt/archive paths below are
outputs; at review time none existed. This command has **not** been run:

The resolved source paths are
`C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\D11_Interior_Standalone_20260927\p\mods_source\models\mods\cat_d11t.tpl.asset\cat_d11t.blend`
and the sibling `export.usf`. The new scratch root will contain
`candidate.usf`, `helper_result.json` and `blender.log`; the separate receipt
and archive will be `operations\d11_wiper_repair_base_probe_01.json` and
`operations\d11_wiper_repair_base_probe_01.json.gz` under the toolchain.

```powershell
$tc = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain'
$env:PYTHONPATH = "$tc\src"
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_authoring `
  --asset cat_d11t `
  --inventory "$tc\operations\d11_authoring_inventory.json" `
  --inventory-sha256 03d3eae96720612ae3b1457a27cc797f8bc6ebb694b230f253bcadbe9d13b50d `
  --blender 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --blender-sha256 e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7 `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script' `
  --scratch-root "$tc\local\wiper-repair-base-scratch-01" `
  --receipt "$tc\operations\d11_wiper_repair_base_probe_01.json" `
  --archive "$tc\operations\d11_wiper_repair_base_probe_01.json.gz" `
  --wiper-scratch-repair --run
```

The predicted first improvement is one animated wiper node with three
36-key splines and the existing actor animation spans. Matching key counts
would not prove matching spline bytes or full asset parity. The hierarchy,
geometry, material, skin and bind differences in the reconstruction worklist
remain, and the native-Blend export gate remains blocked until independently
reviewed asset-specific parity evidence exists.
