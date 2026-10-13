# Reading the retail game's own data

When a rule is unclear, the shipped vehicles are the best evidence: they work. Everything here is
read-only; `roadcraft retail ...` and `roadcraft.retail` read it directly from the installation.

| What | Where (under the game root) | Form | Grade |
|---|---|---|---|
| Retail BROs (trucks, wheels, ...) | `root/prebuild/bro/Bro.Compiled.pak` -> `designer_wizard/<kind>/<name>.bro` | PS text; `roadcraft retail bro <name>` | Retail |
| Compiled truck classes | `root/paks/client/default/default_other.pak` -> `ssl/autogen_designer_wizard/trucks/auto_<truck>/auto_<truck>.cls` | text | Retail |
| Model markups | `root/paks/client/default/default_tpl_*.pak` -> `models/database/vehicles/<tpl>.tpl.asset/<tpl>.tpl_markup` | PS text (masses, constraints, collision groups) | Retail |
| Compiled models | same folder -> `.../tpl/<tpl>.tpl` | binary; `roadcraft tpl-nodes` | Retail |
| SDK type descriptions | `root/prebuild/meta_descs/meta_desc_bro.ps` (and `meta_desc*.ps`) | PS text: members, defaults, hints | SDK |
| SDK samples | `root/mods_source` (TUZ 119 Lynx scout, Aramatsu Crayfish) | editable sources | SDK |

A truck BRO's `tpl` field names its model; the class and markup are found from the truck and model
names. `roadcraft retail find "*armiger*"` lists members by glob.

## Compiled model node table (`.tpl`)

Decoded 2026-09-29 against models whose bone positions were known, and confirmed on the ZiKZ 605E,
Armiger Thunder and the SDK's Lynx sample:

1. `uint32 count`, `uint8 flag`, then `count` names, each `uint32 length` + ASCII (printable; the
   SDK sample has a name with a space);
2. `uint32 n` (= count) and `n` x `uint16` node index;
3. `uint32 nodes`, then `nodes` x 16 `float32`: row-major 4x4 **world** transforms in native axes,
   translation in the last row; rows 0-2 are the node's local X, Y, Z;
4. parent links: an `int16` per node (-1 for the root) earlier in the file, at an offset that varies;
   `tpl_reader.find_parents` finds the array that forms one tree and best matches the IK naming.

Unnamed nodes exist (LOD copies): `nodes` can exceed the name count.

Per-object extents: the compiled `.tpl` also stores float32 bounding boxes as six consecutive values
(min x, y, z then max x, y, z, native axes). Scanning for six finite floats with max > min on each axis
found every shoe box of the KGS-25 section at its known Blender bounds, and gave the retail TC305 and
TUZ 303 track shoes (the track-section frame rule in tracked-vehicles.md). Geometry itself is quantized
(16-byte vertices) in `.tpl_data`; `.geom_dbg` holds names only. (Build, 2026-10-04, WALL-E)

BRO blocks the generator drops: a track's `trackOverlay` (`OverlayPainter`, caterpillar textures) in the
KGS-25 BRO reaches neither its compiled class nor any retail crawler class; judge such blocks by the
compiled class (Build/Retail, 2026-10-04).

## Surveys worth repeating

- `roadcraft retail survey`: implied suspension beta of light 4-wheel retail vehicles
  (see suspension-and-wheels.md).
- Effector kinds over all retail IK chains (ik-visual-rigs.md).
- Which retail trucks have `axleControllerSettings` (84) and in which form.
- `roadcraft retail tracks [truck]`: every crawler's tracks, each wheel's role, axle kind, the body
  it hangs on and whether it reaches the ground, with RC046-RC048 flags (33 vehicles,
  tracked-vehicles.md).
- Does `strength` scale with the vehicle's mass? 16 wheeled retail vehicles of 1.5-40 t, assuming
  each rests as modelled (sag = height): read as relative to the mass (sag = share / (strength x
  beta)) beta has median 69 and log-sd 0.63; read as absolute, log-sd 1.09; the slope of log beta on
  log mass is -0.20 (0 would be relative, -1 absolute). Relative fits better, with wide scatter
  (**Inferred**; a one-off script in the KGS-25 drive-fix workspace, `tools/strength_scaling.py`,
  result in `reports/strength_scaling.json`). It cannot show how frame-hung wheels scale: every wheel
  there hangs on the main body. **Note 2026-10-13** (code analysis, static: `C:\RC_RE\research\physics_semantics.md`, T4/F3):
  code shows no Saber mass scaling of `strength`, and the sag law is Unknown, so this fit is
  statistics over assumed rests, not a mechanism; calibrate per vehicle.

## Local mod activation settings (2026-10-01)

**Retail:** the current Windows retail game stores `UserSettings.enabledMods`
in `%LOCALAPPDATA%/Saber/RoadCraftGame/storage/<platform>/user/<id>/Main/config/
user_settings.cfg`. Observed local entries are `local:<PAK filename without .pak>`;
retain PROS entries and unrelated settings. This is a packed JSON file, not an
editable launcher INI. `GameConfigConsts.ENABLED_MODS_CONFIG` is `enabledMods` in
`default_ssl.pak`, and `DownloadedModsManager` exposes the enable/disable calls and
`local:`/`pros:` prefixes. The prior conclusion that no editable activation state
exists was too definite; absence of a text INI does not establish that.

**Retail, codec 2:** the `SSF1` container has 53 header bytes: magic (4), packed
length (little-endian uint64), raw length (uint64), lowercase ASCII MD5 of the
stored payload (32), and codec byte (1). The payload is a zlib stream transformed
with key bytes `9d 64 aa ec`. State starts with key index, count and marker zero.
When count equals marker, copy the next byte unchanged, set marker to that byte
and count to zero. Otherwise XOR with the next cyclic key byte and increment
count. Do not restart the key index at markers. The transformation is symmetric.
Validate the outer lengths/MD5 and inner zlib Adler-32 before parsing UTF-8 JSON.

Evidence: the inspected retail executable's codec-2 vtable at RVA `0x3b68198`,
transform at `0x23311c0`, and seed assignment `0xecaa649d` at `0x18e5e6`;
current executable SHA-256 is recorded in the helper's `evidence.json` as a new
snapshot, not an accepted pin. Nine observed config files decoded with valid
lengths, MD5 and zlib checksums. The exact 50-byte platform config payload is
retained as a non-personal fixture in `tests/test_offline_mod_activator.py`.

**Build:** [Windows Offline Mods](../integrations/windows-offline-mods/README.txt)
is a portable .NET Framework GUI that changes only the selected local list entry,
retains other JSON text, refuses running RoadCraft/editor processes, atomically
replaces settings and retains exact previous bytes as backups. Its five Python
integration tests invoke the C# application and independently check zlib output,
JSON preservation, corruption refusal, transactions and backup restoration;
the application also runs 17 checks on a supplied settings copy. Run the focused
tests with `python -B -m unittest discover -s tests -p
"test_offline_mod_activator.py"`; Windows and its .NET Framework compiler are
required. `ROADCRAFT_TEST_TMP` can choose a permitted scratch directory.

**Inferred/Open:** editing this state should bypass the browser's local activation
step. Actual activation after retail startup, first-time PROS linking requirements,
save-driven mod selection and multiplayer effects have not been tested. This
does not download PROS mods or grant game acceptance. Config codec 2 is distinct
from legacy CompleteSave chunked compression: ordinary zlib at offset 53 and
fixed-byte XOR attempts failed. Preserve those distinctions. Future codecs or
seed changes must fail safely, not be guessed or written over.

## Native binary and SSL research (2026-10-10)

**Retail, static inspection:** `Roadcraft - Retail.exe` version
`7.4.PATCH.763699 Art: 767189` is AMD64 PE32+ with no CLR directory.
Readable ASCII names include `PropTerraformingBucket`, `TruckEngineParams`
and `TruckEngine`. These are anchors for tracing references in a native
reverse-engineering tool; names alone do not establish a callable mod API.
The version and current SHA-256 snapshot are recorded in workspace receipt
`binary_research_20261010/evidence.json`. Re-establish addresses against the
matching executable before reusing any earlier crash offset or native probe.

**SDK, extracted source:** existing Roamer evidence under
`port_roamer105/reports/native_controls_sources/` contains readable `.ssc`
SSL source. `prop_truck_axles_controller.ssc` declares a branded property,
its imports and initialization body, then delegates to
`native func InitNative(truck : PropTruck)`. That native implementation is
absent from the SSL source. Read SSL bodies, metadata, resource links and
retail classes first; decompile native functions where those sources end.

**Open:** `port_roamer105/reports/custom_vehicle_ssl_feasibility.md`
previously established an internal module resource structure but did not
prove compiling, registering, packaging and normally loading a new custom
vehicle property. This task did not revalidate that route on the current
build. It also did not decompile code or test a new feature, retail startup
or co-op behavior. Do not infer source recovery or loadable custom scripts
from a readable PE or a resource descriptor. A shared validator is premature
until a repeatable feature-specific compile/load experiment establishes the
contract.

### Forklift feature candidate (2026-10-10)

**Build, source inspection:** Red Forklift 35's current BRO assigns manual
`mast_lift`, `fork_lift` and `mast_tilt` actions. Its
`tools/loader_config.py` specifies a fixed selectable crawl angular-velocity
setting of `.05`; this is not a measured road speed. No automatic rule relating
fork height to drive speed was found in this inspected vehicle configuration.
This is not evidence that the engine lacks an undocumented existing controller.

**Open, proposed experiment:** a vehicle-bound script could initially warn above
a chosen measured fork height, then progressively restrict travel speed while
the forks are raised. Prove normal mod script loading, actual height readout and
supported drivetrain/input control separately. Sounding a warning would not
establish speed control. Runtime behavior, save/reload and co-op remain untested.
Evidence: workspace receipt `binary_research_20261010/forklift_feature.json`,
with source snapshots of `forklift_red_mod/README.md`, its BRO and loader config.
Automation is premature until those interfaces and the script lifecycle are
established by an isolated experiment.

### Advanced SSL feature candidates (2026-10-10)

**Owner feedback:** forklift stacking assistance was declined; the owner asked
for advanced applications on other existing mods. This is feature-selection
feedback, not a runtime failure or evidence of an engine limitation.

**Open, concepts:** Kanga 25 load-dependent crane behavior could use the existing
boom/winch rig, but actual load measurement, a justified capacity model and
script access to input/motor control remain unproved. CAT 793D payload monitoring
and haul-cycle statistics require load/dump readouts, display integration and
optional persistence. EX5600/994 loading a CAT 793D would need native material
pickup, retained bucket contents and receiver load mutation with conserved
material; SSL could coordinate those systems, but does not establish native
terrain capabilities. Do not claim any of these is a buildable SSL-only feature.

Evidence: source/document snapshots in workspace receipt
`binary_research_20261010/feature_candidates.json`. The old `wl994_mod/README.md`
explicitly directs continuation to the newer 994 vehicle project; its prior
loading scope cannot establish the current project's behavior. No package was
built or inspected for runtime acceptance in this review. Shared checks are
premature until a feature's script interfaces and normal-load lifecycle are
proven.

