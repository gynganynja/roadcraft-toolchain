# D11 repaired-only mesh reconstructability — 2026-09-29

A pinned Blender 5.2.0 no-save survey parsed the 52 mesh paths in the accepted
repaired D11 USF that are missing from the historical source Blend. It compared
all 1,213 material-slot strings with the reviewed SDK's
`BlenderToUsfSimpleMaterial` template. **All 1,213 matched the template.**
They represent 112 unique material names; three names
(`mod_cat_d11t_painter_08_l0`, `_l1`, `_l2`) correspond to more than one
material string. The SDK ordinarily derives the serialized name from the
Blender material datablock name, so those conflicts still need an explicit
authoring or writer solution before one scene can represent every slot.

All 52 meshes have one UV set. Forty-nine have no color set; the three
`RearFlex_Ripper_vis` LOD meshes have one. All 51 skinned meshes store four
influence slots per corner, but each mesh actually uses only one, two or three
distinct bones. Their serialized bind-table lengths are 1 (21 meshes), 2
(12), 3 (3), 381 (9), or 382 (6). Each stored corner has one or two nonzero
weights. The already reconstructed blade-roll pivot is the only missing mesh
with nonidentity world/local transforms. This survey describes structure; it
does not prove texture content, tangent generation, binds or native behavior.

A second pinned no-save probe applied the SDK-import/authoring pattern to all
15 meshes in five front, rear, side and inner lens LOD families in one live
Blender scene. It created `_LOD0`, `_LOD1` and `_LOD2` siblings under the
reconstructed rig, as required by the SDK's flat LOD conversion. The
maintained path predictor matched every accepted USF path. The scene grew
from 210 to 225 meshes. Across 949 faces and 2,847 triangle corners, all
projected positions, normals and UVs matched exactly, as did face material/
edge indices, complete material strings and metadata, color-set absence, and
skin indices/weights **after remapping live bone indices by name**. The
materials use in-memory image datablocks with accepted texture names, not
verified rendered texture pixels.

The remaining differences are material to native authoring. The SDK emits
399 live rig bones in every projected lens mesh, while accepted lens bind
tables have two or 381. Tangent component error among nine meshes without a
sign difference reaches `0.0002789348363876343`; six other meshes have a
handedness-sign difference of 2.0. A separate isolation readback found one
such sign difference at corner 46 of the front lens LOD1. No source Blend was
saved, no USF was written, and no native rendering or visual acceptance ran.
The existing pending scratch-export command is unchanged and does not request
this 15-mesh stage.

The exact survey and family probes are versioned at
`operations/probes/repaired_mesh_reconstructability_survey_20260929.py`
(SHA-256 `34a1cafd344a3b05b97c92b16253157f5c9178afc338a56203f643956bfd4034`)
and `operations/probes/lens_families_20260929.py`
(SHA-256 `2af08983c1007a103bf8a4d5d220da5ab4e5d363f9ae2416f5c9701967139d37`).
Copy either unchanged to `RoadCraftToolchain/local/` with its same basename,
verify its hash, and run from the Steam development-package root with:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --background --factory-startup --disable-autoexec --threads 1 `
  --python-exit-code 1 `
  --python 'RoadCraftToolchain/local/lens_families_20260929.py'
```

The survey uses the same invocation with its own filename. Both exited zero
with the accepted inventory, worklist, repaired USF, SDK and Blender pins.
The family probe also pins the source Blend, runs and verifies the existing
four-stage structural reconstruction, and checks source/USF/SDK after the
in-memory edits. These outputs are diagnostic evidence, not an approved
native-Blend export or a route-promotion receipt.
