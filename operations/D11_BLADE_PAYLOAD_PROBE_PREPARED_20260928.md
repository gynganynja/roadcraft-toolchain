# D11 blade-collision payload readback prepared — 2026-09-28

This preparation note predates the two completed readbacks. Their results and
limits are in `D11_BLADE_PAYLOAD_READBACK_20260928.md`.

The reconstruction worklist pairs 60 uniquely named `cdt_blade_0`–`59` meshes
under different native and repaired parent paths. The existing no-save blade
readback matched their source/native/repaired world matrices and USF mesh
counts, but it did not compare their payloads. This new diagnostic is prepared
to compare the source Blend's in-memory SDK projection with the two retained
USFs at **both exact hierarchy paths**. It has **not** launched Blender or
produced a readback result.

The host `src/roadcraft/blender_blade_payload.py` is SHA-256
`b02a9c8de297c1673d93bc353e50f9460daafe94d316b00603fe0d2d6cec9f70`;
the Blender worker `src/roadcraft/blender_blade_payload_worker.py` is
`c6a4b4b0c0639a0b412c917e420d320ff5e0015edd915972ec393875b36d3be6`.
The worker pin is embedded in the host. The host and worker check the existing
blade relocation host
`87b272b4f2b52f29488a4188a7df5c2b5e83bdd03fe70527dc036082cc39a8a0`,
mesh payload host
`2ec3051322517d68b07c99bd94710402bb32d2157e540996814e66e5925a1a4e`,
all 14 reviewed SDK files, the accepted 68-file inventory, source Blend,
repaired USF, retained native USF, worklist, parity summary and reviewed Blender
binary. The accepted Blend is
`1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`;
the repaired USF is
`49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170`;
the worklist is
`a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3`.
The native USF and parity-summary pins are resolved through that reviewed
worklist and verified before and after the readback. The host rechecks the
accepted source inventory after the subprocess, not just the selected Blend.

The worker starts with Blender's factory scene, reads the retained USFs with
the pinned SDK, then opens the accepted historical Blend at frame 1. It
requires exactly 210 scene mesh entries and maps 60 visible source meshes
to the native path beneath `BoneBlade_cdt`. The repaired path inserts
`BoneBladeRoll_cdt`. `UsfMesh.b_read(obj)` projects each source mesh in memory.
The readback summarizes ordered triangle-corner positions and normals, face
material/edge indices, UV layer names and coordinates, packed vertex colors,
and skin indices/weights at float32 wire precision. It emits exact path and
per-field three-way digests with row counts, a bounded complete-row digest,
and unmodified SDK color-cache sizes. The SDK color packer is **unwrapped**.

The worker has no USF writer, Blend save or output-file argument. It returns
`blendSaved: false`, `usfExported: false`,
`nativeBlendExportApproved: false` and `equivalenceVerified: false` for every
relocation. The host rejects changed flags, missing or reordered paths,
incomplete digests and an oversized response. Five synthetic boundary tests
passed with Python 3.12+; they do not substitute for a Blender run.

The proposed exact readback command is below. It accepts only the reviewed
base asset and writes no receipt or output file. **It has not been run.**

```powershell
$tc = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain'
$env:PYTHONPATH = "$tc\src"
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_blade_payload `
  --registry "$tc\project.json" `
  --blender 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'
```

The intended second run substitutes the pinned
`C:\Program Files\Blender Foundation\Blender 5.0\blender.exe`.
Only a successful real readback can supply comparison counts. Even if every
ordered field matches, the diagnostic would not establish material-text or
skin-bone identity parity, inverse-bind parity, tangent equivalence,
collision/physics behavior, animation behavior, native appearance, or parity
for the other asset variants. Face material indices and skin indices refer to
different slot and bone tables in each USF; a matching ordered digest alone
cannot prove semantic equivalence. Four extra native-only blade leaves
`cdt_blade_60`–`63` remain outside these 60 paired paths. The known SDK RGBA
cache lifetime fault can affect an unwrapped packed-color projection, so a
color mismatch would require a live raw-RGBA discriminator before attribution.
The accepted `usf-repair` route and blocked native-Blend export gate remain.
