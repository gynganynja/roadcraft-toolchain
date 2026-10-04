# New mod creation: lessons from the Lada conversion

Use this guide alongside [mod-workflow](mod-workflow.md) when turning supplied
assets into a new mod. It brings the Lada session's supported lessons into the
creation path; the subject articles retain the detailed evidence and exceptions.
The lifecycle guidance applies to other mod types. Apply the vehicle sections
only to the features being authored. Lada dimensions, masses, force values,
gear ratios and feature ranges are examples, not defaults for the next vehicle.

## Establish the source and build contract

Preserve the supplied archive and record its contents before conversion. Measure
scale, facing direction, wheel centres and pivots against the actual source.
Fresh FBX/Blender authoring and repaired compiled assets are different routes;
do not claim recovered source or import another project's rig assumptions.
Select the mod's own registry, machine configuration, receipts and output paths.

Start with the requested usable vehicle: appearance, collision, spawning and
driving. Keep later effects and utility work scoped so improvements do not change
the working handling accidentally. Compare compiled gameplay properties and
asset bytes at each stage, with an explicit list of permitted changes. The Lada
used these comparisons to preserve physics during effects, utility and interior
updates. **Build:** see its v6/v7/v8 candidate results in [case-studies](case-studies.md).

Use pinned inputs and complete stage outputs for selective rebuilds. A geometry
change can reuse verified unchanged compiled textures; a gameplay change can
reuse verified models. Regenerate recipes after inputs change. Do not skip the
vehicle workflow's required prepare/generate checks to obtain a package-only
shortcut. See [build-pipeline](build-pipeline.md) and
[texture preservation](textures-and-materials.md).

## Author the contact geometry before tuning around it

| Check | Transferable lesson and evidence |
|---|---|
| Deformable wheel objects | Compile a mesh named `tire` (for example from `tire_LOD0`) and the rim separately. A tyre material on a combined wheel did not satisfy native startup. **Game, isolated editor:** Lada v1 failed; v2 spawned. |
| Wheel handedness | Inspect the final native rim/object frame as well as authoring and slot frames. Lada's left rim adds a half-turn despite identity slots; blindly mirroring the left source would repeat the error. **Game, isolated editor.** |
| Suspension bounds | Native negative displacement extends the wheel downward. The legacy solver uses body lift; use `native_axle_report` for native bounds, then measure actual resting travel and both stop margins. **Game, isolated editor.** |
| Body collision | Partition source panels before convexification so wheel arches and underbody voids remain open. Check clearance against tyre contact/travel volumes and recompute collision centroid before applying the intended COM offset. **Build.** |
| Worked terrain | Sample physical and visual wheel centres, contact flags, travel reserve, ground material and extrusion while stationary and crawling. A flat pad, ramp or undeformed mud pass does not reproduce deep dozer ruts. **Game, bounded observations; original exact terrain comparison remains Open.** |

Read [frames](frames.md) and [suspension-and-wheels](suspension-and-wheels.md).
The Lada's 54 convex sections and 4 mm simplification tolerance are asset-specific;
that tolerance is relative to each unsimplified hull, not every concave surface.
Keep physical collision and low-detail terrain/VFX volumes separately fitted.

## Tune driving and tyre marks as separate systems

Check forward/reverse response, braking, steering, low-range crawling and upper
gears in the native vehicle. Direction-change delay and clutch timing are
distinct from the upper-gear delay formula and standstill-to-neutral timer.
Use a shipped vehicle of the appropriate class as a reference, then measure the
result. **SDK/Retail; Game owner feedback:** [truck-settings](truck-settings.md).

Oversized or deep-looking tracks alone do not establish excessive vehicle mass.
Inspect soil deformation factors, wheel environment-cylinder width, projected
trail width, parallax and tread repeat separately. The native trail's longitudinal
repeat uses `projection width * TRAIL_DIFF image height / image width`; projection
height/yOffset is a vertical volume, not circumference. Derive dimensions and
tread from the supplied tyres. For custom mod trails, check complete active/default
descriptor parity because mod initialization can reset the active descriptor.
**SDK/Build:** [suspension-and-wheels](suspension-and-wheels.md). Lower deformation
coefficients do not prove a proportional reduction in measured rut depth.

## Make each added feature usable and observable

| Feature | Author and verify |
|---|---|
| Lamps and exhaust | Fit locators to the actual lenses and outlet. Use valid visibility references/inline flags. Check engine-on/off, brake/reverse precedence and visible particles; an SFX amount getter alone did not establish whether exhaust was visible. |
| Winch and recovery | Provide both compiled components and playable targeting/pull/release actions. Fit source and recovery sockets to the chassis frame; test actual attachment endpoints and pulls from both ends. |
| Scanners and radar | Provide enabled control sections, named actions, usable radius/effects and costs. Verify scan effects and map reveal. The explorer's `fuelCost` uses recovery tokens; a scene-placed truck can cache an empty level before editor initialization, so check fixture ordering before changing the vehicle. |
| Cockpit | Fit visual bones and keep housings/boots/columns fixed. Verify motion with the high-poly first-person cockpit active. Calibrate needles to the printed dial and actual native normalization; use measured speed/RPM and allow for damping. Zero-align the source needle and preserve opacity or use a fitted silhouette. |
| Wipers | Export separate non-looping forward/return clips, bind their exact names and fit rotation axes to the windshield. Test normal rain activation, both directions and stable parked return. Holding adjacent boundary keys fixed the native exporter's initial one-frame offset on this Lada. Blade motion does not implement a glass-clearing shader. |

**Retail/SDK and Game, isolated editor:** [cockpit-and-lamps](cockpit-and-lamps.md)
and [truck-settings](truck-settings.md) contain the source references, measured
results and limitations. Visual bones alone need not add serialized controllable
joints. Preserve existing controllable IDs when extending a vehicle already in a
save; assess save migration separately if those identities actually change.

## Reuse the checks that already exist

These are opt-in Python helpers, not automatic features of every new starter.
Call the relevant helper from the mod's validation adapter, fail on its reported
issues, and pin its source in the recipe. The Lada's adapters demonstrate wiring.

| Shared helper | Input and scope | Lada wiring |
|---|---|---|
| [native_suspension](../src/roadcraft/native_suspension.py): `native_axle_report`, `travel_has_reserve`; with the measured stops (2026-10-02) `stop_positions`, `position_from_travel`, `design_axle`, `rest_report`, `calibrate_beta` | Native axle bounds/static estimate, or measured travel; no universal spring beta. Prefer the measured-stop functions for new work (suspension-and-wheels.md "Stop geometry") | `tools/validate.py`, `tools/summarize_drive.py` |
| [tracks](../src/roadcraft/tracks.py): `track_layout`, `track_findings` (run by `lint-bro`, RC046-RC048) | Crawler track layout against the retail patterns; light welded frames | KGS-25 drive fix |
| [physics_bench](../src/roadcraft/physics_bench.py): `roadcraft bench` | Variants of suspension, wheels, masses driven in the editor on a project copy; owner's go-ahead needed | KGS-25 drive fix |
| [native_trails](../src/roadcraft/native_trails.py): `custom_trail_report` | Compiled wheel trail descriptor, texture sizes and intended dimensions; no soil-depth or appearance verdict | `tools/audit_exterior.py` |
| [native_utilities](../src/roadcraft/native_utilities.py): `utility_action_report` | Resolved gameplay CLS properties and explicitly requested utilities; checks controls as well as components | `tools/audit_utilities.py` |
| [native_cockpit](../src/roadcraft/native_cockpit.py): `cockpit_animation_report` | Compiled properties, node names and clip names for a cockpit with paired wipers; checks references, not motion | `tools/audit_interior.py` |
| [normal_maps](../src/roadcraft/normal_maps.py): `measure`, `to_directx`; `python -m roadcraft.normal_maps MAP...` | A supplied tangent-space normal map's green convention, decided from its own pixels (needs Pillow + numpy); labels are not evidence | WALL-E `tools/build_textures.py` (flips all four supplied maps) |

Geometry fitting and exact vehicle tuning remain project-specific. The cockpit
helper currently requires both dashboard and wiper controllers: do not apply it
unchanged to a dashboard-only vehicle. Source and compiled checks complement
native tests; they do not replace them.

## Keep a short, reliable native test loop

Run live editor work within the owner's existing authorization and availability.
Seal an isolated fixture tied to the exact package. On the observed SDK, freshly
copied sources can hot-reload during startup and request nonexistent generated
`.ssc.resource` files; Lada's launcher waits until creation/write timestamps are
110 seconds old. This is a scoped source-editor workaround, not a universal
retail startup rule. See [build-pipeline](build-pipeline.md) for failed hypotheses.

Confirm the actual Play engine and selected truck with a correlated probe. An
automation ready marker can appear after a crash. Use normal input state when
testing event-driven lamps or controls; physics debug input may bypass events.
Sample transient actions, such as braking, before they end. Read a borrowed
probe's postconditions: a requirement for JOINT records rejected valid Lada body
data because that rig had none. Keep the failed report and use a suitable probe.

After the run, restore controls, close only the owned editor and compare the
fixture against its original seal. Store native telemetry, visual review and
retail/owner acceptance separately. Use the existing transaction workflow for
authorized installs, with the expected prior hash and verified backup.

Evidence map: Lada v2/v3 suspension/startup, v4 contact/collision, v6 effects/trails,
v7 utilities and v8 cockpit/wipers; exact receipts and failed attempts are listed
in [case-studies](case-studies.md). Final v8 is build-012/test-014,
`runtime/interior_v8_final/review.json` and the v8 candidate `interior_result.json`.
Build-011/test-013 were preliminary calibration evidence. Positive owner feedback
on v6/v7 does not grant acceptance to later builds or certify every feature.


## Preserve the source texture budget deliberately

Before AI upscaling or repainting, compare the supplied map sizes with packing
and compiled PCT output. Restoring already-detailed originals can be the faithful
upgrade: Lada v9 restores 4K maps previously packed at 1K. Preview colour and PBR
maps on the actual UVs, preserve normal conventions, and verify the mip chain
from the emitted headers rather than assuming a stock TD fits every resolution.
When resolution changes, allow the expected extra retail `.pct_mip` members
and compare everything outside the intended texture delta to the old package.
**Build / inspected Blender render:** [texture workflow and limits](textures-and-materials.md),
Lada v9 build-015/test-015; no new retail/performance acceptance is inferred.


## Fit the native driver when a visible occupant is wanted

Check `hideDriver`, an existing upright anchor, and native bone-local offset.
The stock driver provides seated idle animation and native occupancy/camera
visibility rules; it is not a custom hand/pedal rig. Fit and review it in the
actual cabin, then test first-/third-person visibility. The SDK can omit a
default `boneName`, so resolve the shipped default during comparison while
preserving strict checks on unrelated gameplay and compiled assets.
**SDK / Game in isolated editor / Build:** [native seated driver](cockpit-and-lamps.md#native-seated-driver-placement-lada-v10-2026-10-02),
Lada v10; offsets and cabin clearances remain vehicle-specific.
