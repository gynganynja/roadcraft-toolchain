# WALL-E stability investigation (2026-10-05)

**Owner in-game feedback (2026-10-05):** r5 fixes the track flapping, which was
the main complaint. The owner says the remaining wandering "isnt that bad".
Keep the installed r5 settings as the working version. The historical numerical
repeat failure remains recorded; this feedback confirms the reported visual
fix and acceptable current handling, not every terrain or maneuver.

The following build and investigation records predate this owner feedback.

## Installed owner trial: r5 (2026-10-05)

The owner stopped further experimentation and explicitly requested the best
version for an in-game test after reporting twelve hours without useful delivery.
The original-size `crawl_radius_reset` configuration is now built and installed
as **OWNER_REQUESTED_INGAME_TRIAL**, not NATIVE_VALIDATED or accepted.

- Package SHA-256: `fe6fd41188940e0a243a9cde8d8f01c22869bcbb9fcba9305ba9fa33282c4ae1` (56,253,269 bytes).
- Installed: `C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\root\mods\walle.pak`.
- Build receipt: `local/jobs/20261005T084226Z-a4a0279e8438/receipt.json`; test receipt: `local/jobs/20261005T084243Z-8bbd0abdde7f/receipt.json`.
- Recipe: `recipes/stability-r5-build-v2.json`, SHA-256 `334cd6fc00ed8ab93973c5bcbb6982e2ae0c507a81d4c05a79b5ff2fbd2fd552`.
- Install receipt: `local/transactions/8ca355d7acf54874a874b86a2326cb65/receipt.json`.
- Previous r2 SHA-256: `dc3936a7d03bb090e41315dc30cb0eb60d56733058d1d9d2f855b08fb4aa5fa0`; verified backup `C:\RC\WallE_RoadCraft_Mod\local\transactions\8ca355d7acf54874a874b86a2326cb65\before.pak`.
- r4 authoring files were preserved in `stability_20261005/source_r4/manifest.json`.

The selected source snapshot is
`snapshots/radius_state_path_straight_1791177004860879600`, manifest SHA-256
`b3cbb29f81322ecaca5f4d18faecea3e5a79a76e054412425e699e85b421cdc8`.
The packaged truck, both physical wheel classes and chassis markup match this
snapshot semantically after the documented editor/package resource rename.
Preview classes receive the corresponding physics settings. Source and compiled
vehicle checks, the final vehicle check, package CRC/resources/byte audit and
the test phase passed. Seven resource paths changed from r2; duplicate archive
occurrences and existing native model/texture assets were preserved. This is a
text-resource package rebuild using the established toolchain route, with no
geometry recompilation required. The first build's source/package newline
mismatch was corrected with explicit LF serialization; its receipt and package
remain preserved. The corrected build passes the original byte-equality audit.

This original-size variant retains the four rigid wheels, 1200kg chassis and
40/60kg wheels. It uses track tension10, angular damping100, all-wheel lateral
support, handbrake0.35, no reverse wheel resistance, no engine torque pulses,
maxDeltaAngVel0.0002, one crawl gear and matching high gear (about3.79km/h),
zero neutral delay, front extraPhysicalRadius0.005 and uniform0.2 body/default/
asphalt friction with lateral multiplier/max velocity1. Other material friction
and the original model/geometry remain unchanged.

Native evidence: `radius_state_path_straight_151004` passed all21 suite checks,
including rest, coasting, normal/harsh turns and partial/full straight paths.
Whole-path lateral maxima were0.198m forward/0.474m reverse at partial input,
and0.403m/0.487m at full input. Eight reviewed stills showed a continuous belt
outline and upright model; shadows obscure some detail, and stills do not
prove every animation frame. A fresh repeat reached0.5497m reverse lateral
deviation and failed the0.5m gate. That failure is retained. No fully fixed
straightness or retail campaign acceptance is claimed. The user now tests the
installed build; further autonomous tuning has stopped.

The remaining size experiments do not establish a hard engine size limit.
`scale2_half_speed_straight_182118` failed forward lateral0.7856m (reverse0.2883m),
log SHA-256 `898891e2bdadc2bcfd9bcca708eb4887fcd46f2fca1455336273243a69b27117`.
Its scaled camera successfully framed the larger robot. The original-size
`central_contacts_probe_straight_183047` failed strongly: forward12.3927m/
75.0775deg and reverse9.6430m/80.3021deg; log SHA-256
`3b7a44775772ed0107b273e741f1725c86c5345cc9af80b0d20791be3019a019`.
Neither is installed. Total completed WALL-E schedules256, including65 State,
plus3 stock controls and1 separate SSL marker park; geometry-only visibility
captures are separate. These last diagnostics are preserved, not proposed next work.

Reusable tooling work from the investigation remains recorded in the shared
physics-bench, build-pipeline and tracked-vehicles articles: observed-input
measurement windows, complete-path/braking evidence and fixed-decimal native
float serialization. Earlier metrics and failed attempts remain historical.
The serializer/vehicle/workflow focused tests previously passed40 checks.

## Historical investigation before the owner-requested trial

**Current status: unresolved handling; no successor installed.** The owner reported
idle belt vibration and failure to drive straight. r2 reproduced both symptoms.
r3 and r4 built successfully but failed native replay and remain rejected.
The original r2 package is still installed; no retail acceptance is claimed.

Tension 10 held the rendered belt outline in reviewed post-drive/idle sequences,
but the isolated tension-only drive still failed straightness. Parameter changes
must pass complete paths, repeat runs, both directions, turning and full throttle.
Original r2 drives much straighter on a verified native static platform than on
the template terrain; this establishes surface sensitivity, not a repaired mod.

**Measurement correction:** earlier whole-phase reports still used nominal schedule
boundaries and could omit early launch samples because probe/writer clocks differ.
The shared metric now follows contiguous observed controls. The initial 144 completed
schedules were recalculated into observed_phase_summary.json; earlier reports are
preserved. Their archived numbers below are nominal-window measurements unless
explicitly marked corrected. No successor was installed using the old metrics.

Low-friction crawl settings improve some paths but have not passed repeated
forward/reverse and full-throttle checks. A front contact-radius adjustment passed
once and failed its repeat; front compliance still exceeded the reverse path
limit. No combination is ready for delivery. The terrain query found flat stone
at all 231 measured points; this does not expose the private contact solver.

Native logs now explain two invalid probes: geometry-only scaling misaligned
track rollers, and full wheel-torque mode left no active rollers. All-sprung
wheels hit an invalid-index assertion with the belt present but load and drive
when all belt properties are removed. That beltless drive also failed reverse;
it localizes a startup problem without providing a usable repair. Ordinary
engine sandbox logs contain assertions omitted from IntegrationStudio stdout.
The temporary local assertion config has been restored to its original bytes.

Normal controller State inputs are now separately verified. One crawl suite
passed partial/full, turns, idle and park, but its fresh repeat reached0.550m
reverse drift and was rejected. Original-size articulated frames and wheel
interleaving also failed. There is still no repeatably validated successor.

A longer track-footprint diagnostic with friction0.4 passed a full21-check
source suite, then failed a fresh identical full-throttle forward path at0.562m.
Its lower-speed version also failed a fresh repeat (reverse braking0.503m).
Coherent double-size State tests passed partial/normal but failed full throttle
(reverse1.096m); reduced speed on that model is under test. Shared PS
numeric output now uses fixed decimal notation after exact native loading
evidence exposed a scientific-notation parser failure. SSL source execution
works after resource registration, but binary packaging remains unverified.

Evidence lives in the WALL-E project's `stability_20261005/`: source snapshots,
raw controls/telemetry, fixed-camera images, observed_phase_summary.json and
CHECKPOINT.json. trial_summary.json is an archived nominal-window report.
The wheel library is now restored from pristine bytes and included in each new
snapshot because the outline diagnostic adds inline wheel descriptors.

Shared integration: [phase metrics and schedules](../../library/physics-bench.md),
[crawler guidance](../../library/tracked-vehicles.md), and
[symptom diagnosis](../../library/symptoms.md). Fourteen regression cases, 25 bench tests and 9 workflow tests passed after the
clock correction; see reports/observed_window_verification.json. Earlier 20/9
verification remains in reports/shared_verification_full.json.

## Preserved investigation checkpoints

The chronological notes below preserve failed approaches and corrected assumptions.
Their provisional statuses and "next" statements describe those checkpoints;
the current status above and the project CHECKPOINT.json take precedence.

## WALL-E r2 follow-up: idle belt and straightness (2026-10-05)


**Game report:** the owner reports tracks vibrating at rest and failure to drive straight.
**Game, isolated native editor:** package-matched r2 reproduced zero-steer wandering
(2.04 m maximum lateral error over 15.72 m settled forward displacement) and visual belt
flutter despite stationary physical wheels. Thus the earlier r5 statement about resting
and driving is limited to its short tests; it did not validate long straight driving or
the animated belt. The scene reports terrain contact, not a verified static pad.

Increasing sideways friction from 0.1 to 0.3 worsened lateral error to 4.23 m. A combined
reduced-power/responsiveness trial barely drove and failed reverse; rotational damping
20 and always-locked differential trials still wandered. A compliant-axle trial stalled
twice before native readiness, so it provides no driving result. Preserve these failures
without generalizing them to other crawler layouts. Evidence: WALL-E
`stability_20261005/bench/runs/`; see physics-bench.md for the new metrics and schedules.
Further cause isolation and a validated candidate are required.

### Rejected damping-only package replay (2026-10-05)

**Game, isolated editor:** the first damping-100/tension-1 trial looked promising
(forward lateral 0.433 m), but exact r3 package replay produced 2.697 m forward lateral
error and 0.624 m reverse error. The five gameplay resource snapshots are semantically
identical, so the discrepancy is not a package/source mismatch. **r3 is rejected and was
not installed.** This corrects any provisional conclusion based on the first run.
Higher damping alone is not a reliable straight-driving fix; repeat tests before installing.
The tension-1 parked belt remedy remains supported independently. Lateral support plus
damping 100 improved straightness but weakened steering (17/27 deg in 4 s), so that setup
also remains experimental. Critical-collision quality alone and disabled wheel-spin impulse
triggers did not solve the wandering. Further steering/contact tests are in progress.
Evidence: WALL-E `stability_20261005/bench/runs/release_straight_051641`, input snapshots,
`critical_straight_052104`, `noimpulse_straight_052413`; candidate registry records rejection.

### Tension-1 conclusion corrected after driving (2026-10-05)

**Game, native framebuffer review:** `stable_rear_straight_00.png` and `_03.png`
still show the upper belt changing outline after the drive, despite stationary chassis
and wheels. The earlier tension-1 parked sequence looked steadier than r2/zero tension,
but it did **not** establish a complete belt fix. Do not release on telemetry alone.
Further belt-tension/geometry diagnosis continues. Rear-only lateral support plus
damping 100 produced two steadier sustained-drive trials (yaw ranges 7.16/5.52 and
8.33/8.97 deg forward/reverse), with wider powered turns. Stock-crawler brake strength
0.35 stopped initial wheel creep in the measured combined run. These remain experimental.
The correctly bounded compliant-axle attempt also stalled before viewport readiness;
no physical outcome is inferred from that startup failure. Steering-curve experiments
did not recover tight powered pivots. All records remain in WALL-E `stability_20261005/`.

### Rear-only support and critical-collision follow-up (2026-10-05)

**Game, isolated editor:** rear-only lateral support, damping 100, parking strength
0.35 and reverse wheel resistance disabled improved forward yaw across multiple runs,
but the longer reverse tests still showed 16-19 degrees settled heading range and
an initial direction kick. Removing engine jerking did not resolve this. The combined
critical-collision trial (`stable_final_straight_055545`, an exploratory name, not a
release) worsened forward deviation to 9.746 m / 34.90 degrees over 30.46 m; rejected.
The simpler `stable_candidate_straight_060258` measured 0.560 m / 6.33 degrees forward
and 0.486 m / 16.15 degrees reverse, with whole-phase reverse yaw -21.1 degrees.
This is not yet a complete fix. Both-end lateral support is being retested with
full-lock steering to assess the straightness/turning tradeoff.

Tension 10, independently, kept the parked belt outline steady in native captures
after sustained driving and coasting (`stable10_*`, `stable_candidate_straight_*`).
Tension 1's earlier post-drive failure remains recorded. Braking strength 0.35 does
not universally eliminate initial physical wheel creep: some fresh-spawn runs still
showed roughly 0.3 rad/s on one wheel while the chassis moved less than 1 mm. Distinguish
that from the large animated-belt deformation. Whole-phase metrics are retained beside
settled windows so launch yaw is not hidden. No successor package has been installed.


### r4 replay and remaining drift (2026-10-05)

**Game, native editor:** all four wheel slots with lateral support, tension 10, damping
100, reverse wheel resistance off and handbrake strength 0.35 produced steady belts and
lower yaw variation. Pre-package straight settled lateral/yaw: forward 0.067 m / 3.65Â°,
reverse 0.132 m / 8.40Â°. Exact r4 replay: forward 1.100 m / 7.96Â°, reverse 0.486 m / 7.39Â°.
Normal turns remained available (63.5/67.2Â° over 4 s, 2.35/2.34 m displacement), but
full-lock turns are wider. r4 is held for further tuning, not installed. It retained 333
of 337 archive member occurrences unchanged; source/BRO mirrors and all build checks passed.

Sideways friction 0.05 worsened both straight directions (2.790/1.310 m lateral). A neutral
steering curve ending at -1 did not recover tight zero-throttle pivots (11.8/14.8 m travelled
over 8 s); an automatic 1-to-2 shift occurred during the first turn. However, the r4 straight
drive stayed in first gear, so shifting does NOT explain its remaining drift. Brief wheel
spin spikes remain; lower torque with this support layout is the next hypothesis, not a fix.

Evidence: WALL-E `stability_20261005/bench/runs/stable_all_straight_060956`,
`stable_all_grip05_straight_061557`, `stable_all_neutral_straight_062136`, and
`release_r4_park_062837`. r4 SHA-256
`dc0432859804ea5eb67d218b46e55ade2922e9286fc2abc3427285203acd6e36`;
recipe `recipes/stability-r4-build-01.json`; build job `20261004T202639Z-985df53414af`.
Whole-phase output has a launch-kick regression; 18 bench and 9 workflow tests pass.


### r4 rejected after repeat (2026-10-05)

**Game, native editor:** the unchanged r4 repeat failed consistency: settled forward
1.404 m / 14.31Â° and reverse 2.282 m / 21.39Â°. It also fails the planned whole-phase
baseline-relative check (at least 25% lower lateral/displacement ratio and 50% lower yaw
range in both directions of every replay). r4 is now rejected and was not installed.
The original 1.100 m replay and all repeat results are retained, not cherry-picked.
Lower torque (7000) with the same four-wheel support improved forward lateral error to
0.110 m, but reverse yaw range grew to 12.98Â° and speed fell; it was not selected.
The belt remained visually steady at tension 10 throughout the reviewed parked sequences.

Next hypothesis is drivetrain topology: separate the differently sized powered front/rear
wheels into a driven rear sprocket and free front idler per side, with proportionate torque
and speed targets. This is experimental and not established as the cause. Retail EPEC
uses side-grouped real end wheels with isRear omitted, so neither interleaving slot order
nor blindly adding isRear flags is supported as a fix. Evidence is under WALL-E
`stability_20261005/bench/runs/release_r4_repeat_straight_064326` and
`stable_halfpower_straight_063619`; exact resources remain in the per-run snapshots.


### Rear sprocket tests did not solve straight driving (2026-10-05)

**Game, native editor; WALL-E only:** on the tension-10/all-lateral/damping-100
base, front idlers (`torqueType=none`) and rear drive, torque 7000 and half-speed
gear table stalled forward (1.60 m settled; one rear spun at 8â€“10 rad/s while
the other barely moved). Restoring the original gear table and locking the
differential in both RB and gearbox controller removed the stall (45.86 m
settled forward, 13.64 m reverse), but normal steering produced only 4.7/3.2
degrees and full-lock steering 2.0/0.5 degrees: rejected. Runtime diff-lock
was verified on. Those two changes were combined, so the cause of the recovered
forward drive is not isolated. Do not recommend permanent diff lock as a crawler
straightness fix without measuring steering.

SDK `PropRigidBodyStabilizer` changes solver deactivation/sleep only; its name
does not imply a heading controller. This inspection does not identify a new
fix. Evidence: `stability_20261005/bench/runs/rear_sprocket_straight_064931`
and `rear_sprocket_locked_straight_065525`; per-run source snapshots retained.


### Contact probes and first no-pulse trial (2026-10-05, provisional)

**Game, isolated native editor:** stronger sideways friction 0.5 on the r4 base
gave settled forward 1.703 m / 14.77Â° and reverse 1.376 m / 13.67Â°; its normal
turns remained available (96.4/85.5Â°). It does not meet the straightness goal.
`useFakeWheels=True` exited before bench readiness; no series was collected and
no handling conclusion is possible. The log ends with normal automation shutdown
and Wwise cleanup assertions; those lines do not establish the underlying cause.

The no-pulse (`jerkingScale=0`) trial on the r4 base improved whole-phase lateral
deviation to 0.101 m over 19.76 m forward and 0.509 m over 14.31 m reverse;
yaw ranges 2.30/9.73Â°. Normal turns were 72.3/67.1Â°. This first run is promising
but repeated validation is pending; no successor has been installed.

A live native probe during this test read equal contact values on all four wheels:
body friction 2, substance friction 1, terrain deformation factor 0, and identical
world axle vectors [0.99880,0,-0.04889]. Thus neither axle toe mismatch nor unequal
material/deformation settings explains that sampled state. Do not generalize this
surface reading to every terrain. Evidence: `stable_lateral05_straight_070252`,
`stable_fake_straight_070723`, `stable_all_nojerk_straight_070924`, and
`nojerk_contact_probe_camera.jsonl` under WALL-E `stability_20261005`.


### No-pulse repeat and contact modifier rejected (2026-10-05)

The no-pulse configuration passed its first two complete straight paths but failed
the consecutive third: whole-phase forward deviation 2.458 m over 18.67 m, yaw
range 12.71Â°. Reduced yaw oscillation alone is insufficient when the complete path
still curves away. It is rejected as a complete fix; no r5 source/package was made.
Normal and harsh steering still worked, and idle settled, so those passes are
retained separately. Evidence: `stable_all_nojerk_repeat_straight_071353` and its
`after_straight`, `after_harsh`, `after_idle` folders.

Disabling the wheel anti-tunneling modifier on the r4 base also failed: settled
reverse deviation 2.363 m over 12.01 m, yaw range 18.72Â°; native flags 0000 verified.
Keep this result as a rejected experiment, not a recommended setting. Evidence:
`stable_noanti_straight_072117`. Current investigation tests wheel mass/contact
geometry; these are hypotheses, not identified causes. A local retail survey of
33 tracked classes found none declaring isUnlockDiffAvrVelocity or useFakeWheels;
the presence of those options on wheeled scouts is not crawler validation.


### Rear-drive isolation and front mass rejected (2026-10-05)

**Game, native editor; same WALL-E terrain scene.** Raising only front wheel mass
from 40 to 90 kg on the no-pulse r4 setup improved forward tracking but failed
reverse: 1.427 m whole-path lateral deviation over 13.73 m. Evidence:
`stable_balanced_inertia_straight_072553`. This is not a validated inertia fix.

The earlier rear-drive trial changed gear scaling and differential locking
together. `rear_unscaled_straight_073050` isolates rear-only drive at torque 7000,
original gears and unlocked differential on the no-pulse r4 setup. It still
wanders (settled forward 2.349 m over 34.55 m, yaw range 14.23 degrees) and
normal steering stalls (only 10.4 / 5.1 degrees in the two turns). Rear-only
drive is rejected in this tested configuration. A new 20-second full-pedal
schedule also wandered forward (settled 6.062 m over 50.83 m); do not compare
that quantitatively against the 0.35-pedal baseline. Full-pedal baseline remains
unmeasured at this checkpoint.

Earlier suspension experiments stalled at the second editor `wait-viewport`,
after the Play command and scene loading, before usable vehicle telemetry. They provide no evidence that suspension
compliance itself fails. Retrying a bounded compliant setup is valid; keep
startup failures separate from drive results. The current narrower-contact
trial and further suspension/damping hypotheses are not recommendations.


### Narrower contact remains inconsistent (2026-10-05)

**Game, native editor; WALL-E only:** contact widths 0.09 m front / 0.14 m rear,
instead of 0.1854 m at all four wheels, reduced driving height variation to about
1.6-2.7 mm. Native width readings confirmed the change. The first drive passed
the existing whole-path screen and steering remained available, but a fresh repeat
failed reverse (1.401 m lateral over 13.27 m, versus r2 1.087 over 13.79 m).
The third drive improved again (0.071 / 0.286 m whole forward/reverse deviation),
so the narrow setup is rejected for inconsistency, not described by its best run.
Evidence: `stable_narrow_contact_straight_073648`,
`stable_narrow_contact_repeat_straight_074119` and `after_straight`.
The next bounded compliant-axle experiment is a hypothesis, not a fix.

**Build:** `straightfull` is now a shared 80-second bench schedule with 20-second
pedal-1 forward/reverse phases. Keep its baseline separate from pedal-0.35
`straight`. Twenty bench tests and nine vehicle-workflow tests pass, including
the regression that rejects full-pedal samples under the partial-pedal plan.
Verification: WALL-E `stability_20261005/reports/shared_verification_full.json`.


### Compliant setup again failed native readiness (2026-10-05)

**Game startup failure, not a handling measurement:** `stable_compliant_straight_074835`
used min -0.02, max 0.01, height 0.01, strength 0.35 and damping 0.25 on the no-pulse
r4 base. It reached Play, loaded resources, then stopped at the second wait-viewport.
A read-only readiness query to its exact engine PID received no reply. The owned
editor tree was verified and stopped; `bounded_stop.json`, the empty query result
and full startup logs are retained in that run directory. The earlier claim that
all spring trials failed before Play was incorrect: their logs also contain Play
before the second wait-viewport. No physical performance is inferred. Generic
shared-texture warnings also occur in successful rigid runs, so those warnings
alone do not establish the cause. The failure's association with compliance is
repeatable here; its native cause remains unresolved.


### More damping and lower centre of mass were insufficient (2026-10-05)

**Game, isolated native editor:** damping 500 on the no-pulse r4 base was read
back as 500, but reverse still deviated 2.438 m over 14.19 m (whole yaw range
17.54 degrees). Normal turns remained 59.2/60.7 degrees; no useful improvement.
Evidence: `stable_damping500_straight_075237`.

Lowering the absolute body centre of mass from [0,0.15,0] to [0,0,0] improved
reverse in its one trial (0.317 m whole lateral deviation), but forward still
deviated 2.511 m over 35.58 m. Native COM [0,0,0] was verified. Normal turns
remained 71.6/72.3 degrees. This is insufficient as a complete straight-driving
fix. Evidence: `stable_com_ground_straight_075746`.

**Validation correction before successor selection:** a baseline-relative
improvement can still permit obvious path curvature, particularly when distance
increases. The project release guards now additionally require <=0.5 m whole-path
lateral deviation in both directions of every retained packaged replay. Existing
>=25% lateral/displacement improvement, >=50% yaw-range improvement, useful travel,
steering, idle and visual checks remain. This strengthens the gate; it does not
relabel any earlier failure as a pass. It is this rig's test criterion, not a
universal crawler validator. No successor has been selected or installed.

The engine-response-only trial is next: retain torque 14000 and maxDeltaAngVel
0.002, change responsiveness 0.25 to the Karelian donor's 0.045 on the no-pulse r4
base. Earlier `gentle` changed torque, responsiveness and maxDeltaAngVel together,
so its stall did not isolate the response setting. An equal-rolling-radius idea
is only a prepared diagnostic; its temporary simplified appearance is not a
release candidate and has not yet been tested.


### Engine response and overall friction follow-up (2026-10-05)

**Game, native editor:** responsiveness 0.045 alone on the no-pulse r4 base did
not fix wandering. Whole-path forward/reverse lateral maxima were 3.020/1.055 m
over 34.68/14.51 m; yaw ranges 16.28/12.65 degrees. Normal turns remained
56.7/58.9 degrees. Calling it a smoother power-delivery setting was a hypothesis,
not a proven effect: forward travel increased in this run. Evidence:
`stable_response045_straight_080225`.

Halving every friction-material coefficient and setting initial bodyFriction 1
was verified natively as bodyFriction 1 at all four wheels. It reduced vertical
variation but complete-path lateral maxima were still 0.664/0.725 m, over
21.88/13.77 m; yaw ranges 10.70/5.15 degrees. Rejected by the strengthened 0.5 m
screen. `stable_bodyfriction1_straight_080659/screen.json` explicitly records
that normal steering was skipped after the failed straight screen; it was not
tested or claimed to pass. This is different from earlier sideways-multiplier
experiments. It is not a recommended all-surface friction change.

`equal_roll_probe` is a prepared/active diagnostic, not a release: rear physical
wheels match front radius/mass and have a downward slot offset; large rear wheel
visuals reuse the existing visual class while upper rollers are temporarily
omitted. This tests a different rolling layout, but changes several linked fields
and its appearance is knowingly incomplete. Check native placement/radius and
restore the original visual layout before considering a deliverable. No handling
result is claimed at this checkpoint.


### Equal-radius, averaging and low-torque diagnostics (2026-10-05)

**Game, private native editor:** `equal_roll_probe_straight_081039` did level
the physical wheel centres (all native radii 0.0735 m; chassis pitch near
0.00022 rad), but whole forward/reverse paths still deviated 1.311/1.979 m
over 27.54/14.44 m. Rejected. Its rear visual wheel appeared horizontal because
the physical slot orientation was reused for a visual wheel; upper rollers
were also temporarily omitted. This diagnostic appearance is not releasable.
The five baseline files were restored before the next variant.

`stable_average_straight_081409` enabled wheel-speed averaging on the no-pulse
r4 base; native `avg 1` confirms application. Whole paths deviated
0.160/0.763 m over 21.42/13.97 m with yaw ranges 3.93/7.68 degrees. Reverse
failed the strengthened 0.5 m screen; the normal-turn follow-up was skipped.
This improved one sample, not repeatably validated handling.

`stable_torque3500_straight_082055` reduced torque from 14000 to 3500 on the
same no-pulse base. Forward travel fell to 4.61 m with 0.701 m lateral error;
reverse stalled at 0.052 m. Rejected for lost drive authority; its small reverse
lateral number does not establish straight travel. No change was installed.

An all-four-wheel locked-differential trial is next. This differs from the
earlier locked rear-drive trial and from the original r2 locked trial. It must
pass straight travel and turning; locking alone is not an accepted solution.


### All-wheel locking and scaled soft contact (2026-10-05)

**Game, native editor:** `stable_all_locked_straight_082416` applied both
ALWAYS/ALWAYS_ON differential fields to the no-pulse r4 setup; native `diff 1`
confirms activation. Whole forward/reverse errors were 0.666/0.300 m over
36.08/15.02 m, yaw ranges 8.91/5.38 degrees. Parked wheel spin was zero, unlike
the small persistent left-rear spin in several unlocked runs. Forward still
failed the 0.5 m screen; no turning measurement was taken for this variant.

The installed SDK schema (`root/prebuild/meta_descs/meta_desc.ps`,
physTRUCK_SOFT_CONTACT_DESC) declares maxPenetrationDepth 0.1 and forceScale /
forceScaleStatic 1 by default. The 0.1 m value is large relative to WALL-E's
0.0761 m front radius, but this inspection alone does not establish causation.
`stable_soft005_straight_082731` enabled soft contacts with an explicit 0.005 m
limit and force scales 1. The front still sank: native first-row front centres
Y 42.5515/42.5522 versus the hard-contact runs near 42.592, pitch about 0.156 rad.
Whole forward/reverse errors 0.542/0.376 m over 9.47/11.53 m; settled vertical
ranges 45.32/22.54 mm. Rejected. The supposed penetration fix did not work;
do not recommend it from schema values or claim a native 5 mm penetration cap.

`stable_no_tracks_straight_083056` stopped during scene SSL descriptor
finalization before Play. Track-dependent outline/fresnel/opacity/phantom/
covering components remained. Only the verified owned editor tree was stopped
(bounded_stop.json); no handling was measured. SDK source confirms those
components require PropTruckTrack. A corrected wheels-only diagnostic removes
them and the track-dependent blueprints; it successfully reached Play. Contact
geometry and track coupling change, so it is a diagnostic, not release content.


### Static-platform isolation of terrain contact (2026-10-05)

**Game, native private diagnostic:** the original r2 vehicle was replayed on a
256 x 256 x 1 m static box (centre Y 44.5, friction 1, restitution 0). The box
is an inline game_object / iactor with Geom and PropPhysBody, body type
RigidBodyShape and shape phys_shape_box. It needs no new mesh. The actor is
not editor-static (so initialization runs); its rigid body behavior is Static.
Four wheels report ground contact, zero terrain fraction and hull Y near 45.018
through parked, partial-pedal and full-pedal phases. `fixture_check.json` in
each phase checks these facts. This validates support above the terrain; an
authored box alone would not have done so.

Whole-phase measurements (launch included):

- straight forward: 17.914 m, lateral 0.126 m, yaw range 2.999 deg
- straight reverse: 12.949 m, lateral 0.215 m, yaw range 1.283 deg
- straightfull forward: 27.908 m, lateral 0.247 m, yaw range 3.295 deg
- straightfull reverse: 13.933 m, lateral 0.059 m, yaw range 1.276 deg

All inputs applied. Settled vertical ranges were 0.49/0.29 mm at partial pedal
and 0.61/0.30 mm at full pedal. The much straighter behavior of unchanged r2
on this surface points to terrain/contact sensitivity in the tiny running gear,
not a constant imposed left/right steering input. This is an inference: the
surface geometry, material/contact path and spawn height differ, so it is not
a matched numerical repair comparison and does not prove one native algorithm
is defective. Existing terrain failures and the 0.5 m terrain release gate remain.

Evidence: stability_20261005/bench/runs/pad_baseline_park_083931,
reports/static_platform_baseline.json and the six-file snapshot including the
modified scene. `pad_fixture.py` restores the original scene for non-pad runs;
the scratch summary now labels the fixture and omits cross-fixture ratios.
No release candidate or installation resulted from this diagnostic.


### Internal supports and terrain full-throttle baseline (2026-10-05)

**Game, native editor:** wheels-only `stable_wheels_only_straight_083444`
still wandered (whole partial-pedal lateral 1.321/0.576 m over 15.54/10.46 m).
The belt is absent in the inspected screenshot. Full pedal also wandered;
removing track generation does not solve straight travel. This diagnostic
changes contact geometry/coupling and removes track-dependent visual/audio
components, so it is not a deliverable.

`stable_mid_fake_straight_084924` added one internal support on each side,
using fakeWheelIds 4/5, 0.04 m radius override and a separate 0..0.03 m axle
(strength 0.001, damping 0.55). Native telemetry confirms six wheels, support
radii 0.0374 m, centres Y42.5584/42.5585 and all six axles aligned with the
chassis. The original two outline wheels and upper visuals were retained.
Whole errors were 0.513/1.206 m over 14.39/9.60 m, yaw ranges 15.36/29.45 deg.
Rejected: reverse wandering and insufficient reverse travel. No steering result
was taken. Extra small rollers are visible inside the belt in the diagnostic.
The existing model builder already documents a rejected rigid-middle-wheel
layout; this separately sprung internal support also failed, without establishing
that support rollers are unsuitable for tracked vehicles generally.

`stable_fake_sprung_straight_084525` used the alternate all-wheel mode with
finite travel and explicit fake spring/damping values. The engine crashed
before usable driving telemetry. This does not identify a specific bad parameter
or prove an unsupported feature; see the readiness-marker lesson in physics-bench.md.

Original r2 terrain full-pedal baseline is now measured:
`baseline_straightfull_085255`. All five inputs applied. Whole forward/reverse
paths travelled 37.663/14.948 m, lateral maxima 1.687/3.916 m, heading ranges
23.636/61.277 degrees. The broader motion window, which includes braking,
reported heading changes +9.4/-55.5 degrees. Its subsequent partial-pedal replay
also wandered; keep this additional baseline, not just the first run.

SDK `prop_truck_friction_updater.ssc` assigns body friction, terrain deformation
and substance friction separately. likeAsphalt defaults false and enables a
speed-dependent friction boost when true; it is explicitly false in WALL-E.
The next isolated variant sets substanceFriction 0 for default/asphalt and the
initial wheel, retaining body grip and loose-surface materials. This is a
hypothesis under test, not a confirmed terrain-resistance fix.


### Hard-surface resistance and grip isolation (2026-10-05)

**Game, native editor, original terrain fixture:**
`stable_hard_resistance0_straight_085755` set substance friction to zero for
default/asphalt only, preserving body friction and loose-surface settings.
Native readback confirmed body friction 2, substance 0 on all four wheels.
The partial-pedal whole phases were promising: 24.628/14.487 m displacement,
0.133/0.314 m lateral error and 3.700/5.644 degree heading ranges. Normal
pivots remained 66.1/68.8 degrees. Sustained full pedal rejected this variant:
49.919/17.409 m travel, lateral 1.537/2.679 m, heading ranges 5.021/25.684 degrees.
This does not establish substance resistance as the sole cause.

`stable_hardfriction05_straight_090615` instead set hard-surface body grip to
0.5 while preserving substance resistance (native 0.5/1.0 on all four wheels).
Whole partial-pedal forward/reverse travelled 18.916/14.123 m with lateral
0.187/0.719 m and heading ranges 7.394/6.647 degrees. Settled vertical ranges
were only 2.68/3.16 mm, but reverse exceeded the 0.5 m path gate; conditional
turn/full-pedal tests were skipped. No installation or acceptance followed.

SDK source confirms `isWheelStabilizationEnabled` blends the visual wheel
position toward a cast result at speed; it is not evidence of corrected
physical steering. The native script declarations expose averaged-differential
minimum torque, but do not document its internal force law; parameter trials
must remain hypotheses until measured.


### Proportional load and differential torque floor (2026-10-05)

**Game, native editor, original terrain:**
`stable_massscale02_straight_090936` scaled the hull and both wheel classes
to 20% mass, and engine torque to 20%, preserving geometry, gearing and mass
ratios. Native readback confirmed hull 240 kg, front 8 kg and rear 12 kg.
Whole partial-pedal forward was straight (19.365 m travel, 0.063 m lateral,
2.687 degree range), but reverse failed (13.883 m, 0.889 m, 20.735 degrees).
Reducing absolute load alone is not a verified fix. This differs from the
earlier wheel-only mass experiments, which altered the body/wheel ratio.

`stable_average_fulltorque_straight_091308` enabled averaged differential
velocity and set its minimum-torque parameter to 1. Whole phases travelled
19.903/14.392 m, lateral 0.184/2.586 m, heading ranges 4.976/21.374 degrees.
Native readback confirmed averaged mode; source snapshots pin the torque-floor
setting. Reverse failed; no steering or full-pedal result was taken. Do not
infer the undocumented native force law from the setting's name.

A separate three-millimetre suspension-compliance variant reached Play and
usable bench startup, unlike prior centimetre-travel failures. Driving results
remain pending; startup alone does not validate suspension or handling.


### Finite compliance, speed attenuation and combined contact trial (2026-10-05)

**Game, native editor, original terrain:** the 3 mm travel diagnostic
`stable_microtravel_straight_091621` reached Play and applied all inputs.
Whole forward/reverse travel 19.368/14.369 m, lateral 1.559/1.655 m and heading
ranges 12.963/17.890 degrees failed. Native rest readings put both front slots
at travel 0 and both rear slots at 0.003 m. This trial did not demonstrate a
suspension operating away from its limits. A front-only compliance experiment
has been prepared, but is not yet measured.

`stable_flat_speed_torque_straight_091946` replaced the speed-dependent
inner-track torque spline with constant 1. Whole travel 29.953/13.704 m,
lateral 0.374/1.649 m and heading ranges 8.205/12.686 degrees: reverse failed.
`stable_hard_contact_straight_092302` combined hard-surface grip 0.5 and
substance resistance 0 (both confirmed by native wheel readback), preserving
loose-surface values. Whole travel 22.490/14.053 m, lateral 0.937/0.681 m,
heading ranges 11.691/6.653 degrees: both directions failed. Turn/full-pedal
follow-ups were skipped for these failed screens. No successor was installed.

Every sampled wheel remained on ground during rest and settled forward/reverse
in original baseline 034400 and the load-scale, microtravel and grip-0.5 trials.
Thus these recordings do not support a claim that repeated loss of ground
contact caused their drift. Grip 0.5 reduced wheel-spin variation, but did not
pass the path gate. Ground presence is not a measurement of normal load.

**Retail:** a source-hashed survey of 33 tracked classes found 30 with at least
one isRear wheel slot and none with explicit enableLateralForce true. Greenway
HT500 and the two Vostok ATM53 variants omit rear flags. EPEC TC305 marks its
internal support wheels, but not the four real end wheels, as rear. Karelian
marks all rollers except its first/front slots and front fakes. These layouts
do not establish a universal required flag or explain the internal native force
law. WALL-E omits isRear on all four slots; a separately measured rear-flag
diagnostic is pending. Survey evidence: reports/native_rear_survey.json.


### Rear metadata and measured front suspension reserve (2026-10-05)

**Game, native editor:** `stable_rear_flags_straight_092634` set isRear on the
two large wheels. Native slot flags read back as 0101; wheel masses stayed
40/60/40/60 kg. Whole partial-pedal forward/reverse: 18.862/13.938 m, lateral
0.055/0.475 m, heading range 2.704/14.404 degrees. Normal pivots were 56.5/73.8
degrees. Full pedal rejected it: 48.142/17.164 m travel, lateral 4.431/3.148 m,
heading ranges 11.143/17.714 degrees. Rear flags alone are not a verified repair.

`stable_front_sprung_straight_093244` kept the rear wheels rigid and used a
second front axle: min -0.008, max 0.006, height 0.006, strength 1, damping 0.55.
Native front rest travel was 0.0051..0.0052 m; moving samples stayed between
0.0025 and 0.0084 m, with all four wheels on ground. This demonstrates useful
front travel reserve for this exact configuration, unlike the earlier 3 mm
all-wheel variant that sat at opposing limits. Handling still failed: whole
forward/reverse 19.208/13.975 m, lateral 0.401/3.052 m, heading ranges
7.989/19.442 degrees. Suspension reserve alone is not sufficient for straightness.

Extending the same axle to all four wheels in
`stable_sprung014_straight_093632` stalled after Play and resource loading,
at the second wait-viewport stage. A direct native readiness probe returned
one missing response (empty JSONL), despite exit code 0. Only the identity-
verified owned studio/engine tree was stopped; launch.json records ready false.
No driving metrics exist. This does not identify an internal solver cause or
prove all-wheel spring support is generally unsupported.

Most recent variants inherited the rejected r4 damping/lateral/brake combination.
They are diagnostic names, not accepted stability settings. A new isolation
returns to original r2 physics plus belt tension 10 and critical wheel collision
quality. Its outcome is pending; do not combine the favorable parts of failed
trials into a claimed repair.


### Original damping and critical collision isolation (2026-10-05)

**Game, native editor:** `critical_taut_straight_094037` restored original r2
physics and changed only belt tension to 10 and critical wheel collision quality.
Native damping was 1.5, critical flags 1111, rear flags 0000. Whole forward/reverse
travel was 19.126/13.824 m, lateral 0.248/1.752 m and yaw range 17.767/13.317 degrees.
It failed. Adding only engine jerkingScale 0 in `critical_nojerk_straight_094406`
also failed: 19.190/13.602 m travel, lateral 1.198/6.041 m, yaw 9.840/35.518 degrees.
No normal/full follow-ups were run after these failed screens.

These original-damping trials matter because most earlier contact experiments
inherited the rejected r4 combination; favorable partial results did not establish
that combination as a sound base. **SDK:** PropTruckWheel exposes
DisableSubstanceTargetAction/EnableSubstanceTargetAction, but no callers were
found in the inspected truck/wheel scripts. A planned runtime diagnostic must
verify ground support and native acknowledgement; the method name alone does
not establish a useful or safe handling remedy.


### Belt-only and runtime terrain-action controls (2026-10-05)

**Game, isolated native editor:** returning to original r2 settings did not make
rear metadata a repair. `rear_flags_taut_straight_094925` (only tension 10 and
rear flags 0101) measured whole forward/reverse 18.293/13.656 m travel,
3.091/0.639 m lateral and 26.907/14.788 degrees yaw range; it failed.

`no_substance_taut_straight_095258` used original r2 plus tension 10, and a
recorded runtime hook called DisableSubstanceTargetAction on all four wheels.
The native acknowledgement reports four calls. Ground support remained and it
travelled 18.159/13.144 m, but lateral deviation 0.677/5.926 m and heading ranges
28.755/52.415 degrees failed. The acknowledgement proves the calls executed;
there is no public readback proving persistence of the internal action state.
This is not a deliverable fix. Runtime hook source and response are in its run.

The matched configuration without that runtime hook,
`taut_only_straight_095659`, also failed: 18.513/12.808 m travel, 0.984/4.797 m
lateral, 29.325/47.056 degrees yaw range. Thus tension 10's visual benefit does
not establish a handling repair. Neither isolation was advanced to release.


### Soft terrain contact and support-layout startup (2026-10-05)

**Game, native editor:** `stable_soft_terrain_straight_100016` enabled soft
contact with static-only false, retaining the failed r4/no-jerk base and authored
maxPenetrationDepth 0.005. It failed: whole forward/reverse travel 10.044/11.389 m,
lateral 0.720/1.544 m, yaw range 9.275/9.900 degrees. Front wheel centres still
rested near Y42.547 versus rear Y42.637 on the original Y42.5 terrain. Native
ground flags stayed true, but forward wheel spin standard deviations reached
4.2..8.0 rad/s. An authored penetration setting is not proof of a measured 5 mm
cap; soft contact did not resolve this miniature crawler's support or handling.

`track_fakes_taut_straight_100343` moved all four original wheels into each
track's fakeWheelIds, emptied wheelIds, and provided the 14 mm travel axle. It
kept global useFakeWheels false and original r2 driving settings plus tension 10.
The editor stopped progressing at the first wait-viewport, before Play. Unlike
the earlier post-Play spring stall, a direct native probe did respond. No driving
telemetry exists. The owned process tree was stopped with identity and response
recorded in bounded_stop.json. This is a startup failure, not a handling result.

The follow-up adds one raised real drive wheel at each nose roller and is being
launched only after source files age 110 seconds, following the existing
Lada/Roamer SDK timing finding. It has no result yet. Do not assert whether the
prior failure was caused by missing real wheels or source-reload timing.


### Explicit outline and hidden-wheel effects (2026-10-05)

`supported_outline_taut_straight_102100` added front/rear visual rollers through
inline descriptors in the wheel library, retained four sprung hidden supports,
and used two smaller raised real drive circles inside the nose rollers. All
source files aged at least 110 seconds. It still stopped at first wait-viewport,
before Play; a direct native probe responded. New native errors specifically
reported missing covering support on the hidden wheel actors' DUMMY templates.
They are recorded in stdout.log and bounded_stop.json; no handling was measured.

**SDK/Retail:** the shipped ATM53 fake-wheel class omits Geom, PropCovering,
PropOutline, PropFresnelHighlightRb and Vfx, while keeping wheel physics info,
friction, wheel particles and trails. The prepared cleanup removes those visual
effects from the hidden physics actors and keeps them on visible rollers.
This resolves an identified descriptor mismatch in source; native startup and
driving are not yet verified. Do not assert the covering errors were the sole
cause of the startup failure. The smaller `front_support_outline` trial keeps
the original rigid rear drive wheels, changes only the front pair to sprung
support IDs, and adds matching front visual rollers. Its result is pending.


### Real-roller count and front-support startup (2026-10-05)

`front_support_outline_straight_102612` removed hidden-front covering/outline/
fresnel/Vfx effects, kept rigid real rear wheels, and used sprung front support
IDs with explicit front visual rollers. The DUMMY covering errors disappeared,
but the editor still did not pass first wait-viewport before Play. A direct native
probe returned no current truck; a screenshot was requested but no PNG was
produced. The source-age wait and bounded-stop identity evidence are retained.
The descriptor correction did not establish a working vehicle.

**Retail:** all 33 inspected tracked classes have at least two wheelIds per track
(78 tracks total: 26 with two, 2 with three, 10 with four, 2 with five, 20 with
seven, 10 with eight, 4 with ten and 4 with eleven). Source hashes and counts are
in reports/retail_track_counts.json. The preceding all-support/raised/front-support
experiments supplied zero or one real roller per side. **Inferred:** this shared
difference may explain their pre-Play failures; no native minimum is documented
in the exposed script, and there is no universal validator yet. The next trial
`front_support_two_real` adds one contained, raised real nose roller per side to
the front-support setup, giving each side two real rollers. Its result is pending.


### Complete wheel registration loaded; support trial rejected (2026-10-05)

The two-real-roller inline trial `front_support_two_real_straight_103256`
still failed first wait-viewport. Registering the same visual descriptor as a
separate class and linking it from the aggregate library allowed the editor to
reach Play (`front_support_registered_straight_103903`), but the truck was absent.
A native probe returned `WHEEL_LIBRARY LIVE_FOUND LIVE_NEW_MISSING CURRENT_TRUCK_NONE`.
The descriptor equivalence report preserves that this registration step changed
resource identity, not the intended physics values.

Adding the descriptor to `auto_walle_truck_wheel_info.sso` and its resource links
completed the lookup chain. `front_support_complete_straight_104436` loaded the
truck and applied all five controls. It failed: complete forward path 5.036 m,
1.342 m lateral, 36.503 degrees yaw range; reverse 4.936 m, 1.330 m, 27.303 degrees.
The four ground wheels reported contact throughout measured phases; the two raised
nose wheels remained off ground and spun rapidly (forward means 24.88/29.16 rad/s).
Those raised wheels inherited driven torque, so the next isolated layout trial
will make them passive. This is a hypothesis, not an identified handling fix.

**SDK/Game:** WheelsLibrary.Get resolves the live truckWheels table. For this
WALL-E editor fixture, editing only initialChunkTruckWheels did not register a new
visual wheel in that table. New class, per-truck wheel-info entry and dependency
links were required to reach a drive. The earlier real-roller-count explanation
was unproven: all retail counts remain evidence, but do not establish the cause
of these earlier startup failures. Do not turn that hypothesis into a validator.
Evidence: exact snapshots, native probe/replies, bounded-stop records, and
reports/registered_visual_equivalence.json in stability_20261005.


### Passive raised wheels and isolated original settings (2026-10-05)

`front_support_passive_nose_straight_105503` changed only the two raised nose
wheels' torqueType to none versus front_support_complete. Whole travel recovered
from 5.036/4.936 m to 18.224/13.336 m, but lateral deviation worsened to
3.409/5.641 m (yaw range 27.871/52.355 degrees). This supports off-ground driven
wheels as the preceding diagnostic's traction problem, not the original mod's
handling cause. The support layout remains rejected.

Two isolated changes on the original r2 geometry/physics plus tension 10 also
failed. `no_antitunnel_taut_straight_104948` confirmed native anti flags 0000 and
measured 1.582/1.480 m lateral over 18.645/13.631 m; yaw 27.365/28.727 degrees.
`nojerk_taut_straight_105823` removed engine torque pulses and measured
1.505/3.411 m lateral over 18.149/12.964 m; yaw 37.098/38.663 degrees.
These differ from the older r4-based no-anti/no-pulse trials and are not fixes.

**Game, native telemetry:** the no-pulse r4 trial at 0.35 pedal stayed in first
gear in 070924; its independent 071353 repeat shifted through second to third.
The 101313 front-radius trial's full-pedal follow-up reached fourth and about
3.48 m/s. Thus equal pedal commands do not guarantee matched achieved speed or
gear history. Retain actual gears/speeds along with whole paths. The next crawl
diagnostic limits the existing front-radius configuration to its original first
forward gear; that changes usable road speed and is not yet a validated fix.
Source/readback limits: the exposed SDK scripts contained no invocation of
EnableSubstanceTargetAction/DisableSubstanceTargetAction outside their native
declarations; this does not prove native code never re-enables the action.


### Corrected observed-input windows and later diagnostics (2026-10-05)

**Correction, Build/Game:** the earlier "whole-phase" values still used nominal
schedule boundaries. The probe starts its clock after receiver registration, while
the writer starts earlier. In the uniform-contact run, forward input was already
observed at probe t=11.619 s, before the nominal t=12 boundary. Omitting that
fraction of launch can change the reference heading and cross-track result.

Shared phase_stability now offers observed_windows=True. A nominal window locates
the matching contiguous input run, then measurement extends to both observed
control transitions. Separated matching runs fail closed as ambiguous. Whole
measurements include launch and gearbox transition, with no actual-gear filter.
physics_bench.analyse wires this into stabilityWholePhase and adds stabilityObserved
for settled observed windows. stability and stabilityPlannedWholePhase retain the
nominal-window calculation. Five new regressions cover early launches, late input
ends, repeated controls separated by braking, fragmented input, settling and
missing anchors. All 25 bench tests and 9 workflow tests pass.

All 144 completed recorded schedules were recalculated into
observed_phase_summary.json with raw-series and legacy-summary SHA256 values;
no prior per-run summary was overwritten. No ambiguous input phase was found.
Use this corrected report for comparisons. Earlier checkpoint numbers are legacy
nominal-window measurements, not complete observed-input phases. New r2 baseline:
forward 18.364 m travel, 2.244 m lateral, 27.882 degrees yaw range; reverse
14.016 m, 2.111 m, 32.496 degrees. Full-pedal r2: 37.711/15.349 m travel,
1.907/4.637 m lateral, 23.636/61.277 degrees yaw. The absolute 0.5 m release limit
and repeated-package/turn/idle/full-throttle requirements remain unchanged.

Recent rejected diagnostics, now with corrected observed windows:
the lower-speed front-radius trial failed reverse; equal-radius locked diagnostic
also failed. Uniform contact friction (body/asphalt/default 0.4, sideways multiplier
1) had reverse 0.048 m deviation over 13.938 m, but forward 0.963 m over 21.979 m;
its forward gearbox climbed from first through third. The next uniform-crawl test
restricts forward gearing and remains provisional. Frame counts were about
59.7 frames/second over each inspected complete recording, excluding gross frame
rate differences as an explanation for these particular differing runs.

The active crawl trial's native water probe read waterDepth=0 and mudDepth=0 on all
four grounded terrain wheels. This is an instantaneous check, not a survey of
all terrain. Disabling both copied chassis engine shakers on otherwise original
r2 (`no_shaker_original_straight_111157`) still failed: 3.335/2.359 m lateral over
18.215/13.622 m, yaw 43.578/25.566 degrees. Reviewed post-drive frames still show
an unsuitable belt outline; the shakers are not an established remedy. SDK shaker
offset curves are RPM based; their native force/visual implementation is hidden.


### Uniform contact follow-ups with corrected windows (2026-10-05)

All values below use complete contiguous observed input phases. Each run applied
all five inputs; none passes the unchanged 0.5 m lateral gate in both directions.

| Native run | Forward: travel / lateral / yaw range | Reverse: travel / lateral / yaw range |
|---|---|---|
| `stable_uniform_crawl_straight_111634` | 18.964 m / 0.570 m / 12.366 deg | 14.159 m / 0.251 m / 6.008 deg |
| `stable_uniform_crawl_delta_straight_112016` | 18.725 m / 0.207 m / 8.257 deg | 14.159 m / 0.618 m / 6.101 deg |
| `stable_uniform_crawl_nosub_straight_112403` | 18.781 m / 0.709 m / 12.896 deg | 14.118 m / 0.140 m / 5.852 deg |

The crawl version limits forward gearing to first. The delta version additionally
reduces maxDeltaAngVel from 0.002 to 0.0002. The nosub version then removes
default/asphalt substance friction (native readback 0 on all four wheels).
A good direction in one test does not validate the complete configuration.
Normal/full-pedal follow-ups were skipped by the provisional straight-path screen.

The next `large_sprung_support` diagnostic keeps the original real/visual track
layout and adds one hidden 0.15 m radius sprung support wheel inside each track.
It uses complete per-truck/aggregate wheel registration, an explicit source-age
wait and snapshots of both shared runtime analysis modules. This is a geometry
hypothesis, not a selected repair. A read-only native inertia probe is also added;
its result and interpretation remain pending.


### Larger support and lower COM results (2026-10-05)

Complete observed-input phase metrics; all five commanded inputs applied.

| Native run | Forward: travel / lateral / yaw range | Reverse: travel / lateral / yaw range |
|---|---|---|
| `large_sprung_support_straight_113113` | 0.815 m / 0.099 m / 12.575 deg | 11.595 m / 8.698 m / 98.964 deg |
| `uniform_crawl_ground_com_straight_113517` | 18.988 m / 0.916 m / 8.741 deg | 14.075 m / 0.542 m / 8.495 deg |
| `uniform_crawl_ground_com_straight_113517/after_straightfull` | 20.069 m / 0.978 m / 7.058 deg | 14.887 m / 0.638 m / 7.569 deg |

Both configurations are rejected. Larger sprung contacts nearly stalled forward
travel. The nominal settled contact diagnostic showed only the two original
front wheels grounded during forward travel: both rear wheels and both added
support wheels were airborne. It is therefore unsupported to say the new
middle wheels held the originals off the ground.

Lower COM retained normal steering (89.8/88.1 degree pivot magnitudes) but
failed straight travel at both partial and full throttle. The first inertia
probe on the support test failed because StringFormat exceeded its argument
limit; splitting the formatting allowed the ground-COM probe to return a
symmetric world-space response matrix. A heading correction was considered,
but no supported packageable custom controller has been established. No
runtime-only correction is being substituted for a distributable mod fix.

The next test combines differential locking with the bounded first-gear
uniform-contact configuration. Earlier locking tests used different friction
and the original multi-gear drivetrain; this trial isolates locking on the
current crawl base and includes steering/full-throttle follow-ups.


### Differential lock fails steering (2026-10-05)

**Game, native editor; corrected observed windows:** `uniform_crawl_locked_straight_114410`
confirmed the live differential lock enabled. Partial-pedal forward measured
19.619 m travel / 0.132 m lateral / 5.038 degree yaw range; reverse measured
14.399 / 0.683 / 9.180. Full pedal failed too: 20.228 / 1.171 / 7.152 forward,
15.121 / 0.521 / 6.135 reverse. All straight commands applied.

Normal steering was materially worse: the positive and negative pivot phases
produced only -7.8 and -12.7 degrees, with 4.45 and 2.45 m displacement. Both
turns went in the same yaw direction rather than supplying opposite pivots.
All nine commands applied. This combination is rejected independently of the
straight-path failure. A future comparison must not select locking solely from
the good forward result. Retail survey found 658 tracked slots with torqueType
defaults and 12 passive slots across 33 classes; no tested evidence supports
changing them to full as a remedy.

Read-only chassis impulse-response probes at three orientations, transformed
back to the body axes, were approximately diagonal (70.5494, 66.5522, 83.2757),
with absolute off-diagonal terms below 0.0001. This does not support asymmetric
chassis inertia as the cause in that ground-COM configuration. It does not
establish that other wheel/contact forces are symmetric.

The next isolated test removes the extra wheel lateral-force correction from
the unlocked uniform-contact crawl base. A separate named compliant axle is
prepared but untested: earlier all-wheel spring trials modified index zero and
failed native readiness; the working front-only trial appended a named axle.
The index distinction is a hypothesis, not a demonstrated startup fix.


### Lateral-force isolation and repeated all-sprung startup failure (2026-10-05)

**Game, corrected observed windows:** `uniform_crawl_no_lateral_straight_115019`
disabled all four extra lateral-force flags on the unlocked uniform crawl/delta
base. Forward measured 18.739 m / 0.139 m lateral / 9.313 degrees; reverse
14.140 m / 2.640 m / 15.231 degrees. All five inputs applied; steering and full
throttle were skipped after the failed screen. Reject this configuration.

**Startup only:** `uniform_crawl_sprung_named_straight_115548` added a new named
14 mm axle and assigned all four existing wheels to index 1, preserving rigid
index 0. Even after the recorded 110-second source-age interval, it stalled
after Play/resource loading. A read-only native query returned no response;
the unique owned studio/engine IDs and run creation time were checked before
stopping them. No driving telemetry exists. This rejects the hypothesis that
merely moving the compliant axle away from index zero resolves readiness.

The larger-support trial's full phase report also records chassis pitch up to
80.79 degrees during forward travel; this explains why only its two front
wheels stayed grounded. The earlier contact-only note omitted this major
failure. Its stop phase remained strongly pitched; the final parked image was
taken after reverse brought the vehicle back down. A final capture alone does
not describe what occurred during the drive.

The next controlled test increases only chassis mass from 1200 to 3000 kg on
the working uniform crawl/delta base. A separate all-sprung layout with one
small passive raised rigid wheel per track is prepared, not validated; it asks
whether track initialization requires a stable raised anchor in this layout.
That hypothesis is not a universal track rule and has no shared validator.


### Mass, raised anchors and response follow-ups (2026-10-05)

Corrected whole observed-input phases; both drives applied all five commands.

| Run | Forward travel / lateral / yaw range | Reverse travel / lateral / yaw range |
|---|---|---|
| `uniform_crawl_bodymass_straight_115914` | 18.458 m / 1.005 m / 10.243 deg | 13.763 m / 0.620 m / 4.073 deg |
| `uniform_crawl_response045_straight_120759` | 19.431 m / 0.926 m / 9.519 deg | 14.567 m / 0.382 m / 3.702 deg |

Both failed the 0.5 m gate; turn/full follow-ups were skipped. Native mass was
3000 kg in the mass trial, with the expected higher impulse response. That
setting did take effect but did not fix straightness. The response trial
changed only engine responsiveness to 0.045 on the uniform crawl/delta base.
Its reverse result is promising in isolation; its failed forward path rejects
the complete configuration.

`uniform_crawl_sprung_anchor_straight_120504` added a passive hidden rigid
0.025 m roller at each raised nose location, retained the original four
sprung ground wheels and registered the descriptors in both wheel libraries.
After the recorded source-age wait it again stalled after Play/resource
loading. No native readiness reply or drive telemetry existed. The owned
engine/studio were identity-checked and stopped; bounded_stop.json preserves
the details. A raised rigid anchor did not resolve this startup failure.

The isolated local runner now accepts a recorded startup timeout (120â€“600 s);
the response trial used 180 seconds and started normally. The shared launcher
default is unchanged. Syntax checks passed for the local helpers.
The current next contact test uses hard-surface friction 0.2 instead of 0.4
on the original uniform crawl/delta base. No repair is selected or installed.


### Flat terrain confirmed; friction and neutral follow-ups (2026-10-05)

**Game, read-only native terrain query:** 231 grid points at X0..10/Z0..50 m
(1/2.5 m spacing) all returned height 42.499123 m, normal [0,1,0], extrusion 0
and material stone. Evidence: `uniform_crawl_neutral_reset_straight_121750/terrain_grid.jsonl`
and `reports/terrain_grid.json`. The earlier static-versus-terrain distinction
remains valid, but the visible rocky texture is not evidence of height variation.
These samples do not query every physical object or expose the private wheel solver.

`uniform_crawl_friction02_straight_121130` reduced default/asphalt contact
friction from 0.4 to 0.2 on the uniform crawl/delta base. Partial straight passed
one screen (18.845/13.719 m travel; 0.133/0.207 m lateral; 4.230/4.150 deg yaw).
Normal turns achieved -67.7/+71.9 degrees. Full throttle rejected the setup:
20.127/15.048 m travel, 2.663/0.176 m lateral, 10.548/2.841 degree yaw ranges.
Native friction was 0.2 on all four wheels. Preserve the failed full drive.

Telemetry showed actual gear 1 or -1 retained through stops with the 60-second
neutral delay, even when wheels were nearly still. The next trial changes only
neutralGearSwitchingDelay to 0. Its native stop/final samples do return gear 0,
so the setting is effective. Initial partial paths measured 18.694/14.059 m,
0.119/0.461 m lateral, 3.722/13.642 degree yaw ranges; normal turns were
-50.2/+60.7 degrees. Full throttle and repeatability remain pending at this
checkpoint. Retained gear is a diagnostic hypothesis, not yet a proven cause.


### Neutral, rear flags and contact width rejected (2026-10-05)

**Game, complete observed input windows:** the immediate-neutral trial
`uniform_crawl_neutral_reset_straight_121750` failed its full-throttle reverse:
forward/reverse travel 20.058/14.973 m, lateral 0.498/0.652 m, yaw range
8.176/8.357 degrees. Returning the actual gearbox to neutral at stops works,
but does not establish a straight-driving repair.

On that same friction-0.2/neutral-0 base, `crawl_rear_reset_straight_122414`
corrected the rear-slot flags to 0/1/0/1. Partial travel 18.997/13.982 m,
lateral 0.661/0.654 m and yaw range 8.260/7.569 degrees failed the screen.
`crawl_narrow_reset_straight_122739` instead narrowed front/rear contact widths
to 0.09/0.14 m: travel 19.131/14.106 m, lateral 1.151/1.016 m and yaw range
10.949/8.009 degrees. Native widths were confirmed and the body was nearly
level; this still failed. Follow-up turns/full-throttle schedules were skipped
for both failed screens. Preserve every run; no configuration is selected.

Next diagnostic: a 0.005 m front physical-radius correction on the same base.
This is isolated fixture work. Installed r2 and authoring r4 are unchanged;
r4 remains rejected and no r5 source or package exists.


### Front radius passed once, failed fresh repeat (2026-10-05)

**Game, complete observed windows:** `crawl_radius_reset_straight_123727`
adds 0.005 m extraPhysicalRadius to both front slots on the friction-0.2,
neutral-0, bounded crawl/delta base. Native front physical radius was 0.0785 m
(rear 0.1134 m), all four wheels reported terrain contact. Partial paths:
19.528/14.738 m travel, 0.193/0.033 m lateral, 6.923/4.148 degree yaw ranges.
Normal turns achieved -62.2/+56.1 degrees. Full-pedal paths measured
20.495/15.310 m, 0.413/0.413 m lateral and 4.356/4.312 degree yaw ranges.

The fresh repeat `crawl_radius_repeat_straight_124354` measured
19.427/14.405 m, 0.179/0.534 m lateral, 5.357/11.939 degree yaw ranges.
Reverse exceeded the established 0.5 m limit. The configuration is rejected
for repeatability; all scheduled follow-ups after this failed screen were
skipped, and no package was prepared. The passing first run is not a release.

Next diagnostic `crawl_radius_slow` keeps those contacts and reduces first/high
angularVelocity from 2 to 1, reverse from 0.75 to 0.65. This is a speed tradeoff,
not a confirmed fix. The >10 m path requirement and all other gates remain.

**SDK:** prop_truck_view_controller.ssc UpdateSteering uses
steerRotateEngineControl only to suppress steering while the SSL engine is
stopped; this is not a heading-hold flag. FrictionMaterial.likeAsphalt applies
a speed/slip-dependent body-friction update, not a switch from terrain to
static collision. Neither setting is established as a remedy.

The local runner now writes a source_snapshot.json link into each main and
follow-up run, pinning its snapshot manifest and copying a package identity
when replaying a built candidate. This improves future replay traceability;
earlier snapshots and run reports remain untouched. Syntax checked.


### Lower speed and soft front contacts failed (2026-10-05)

**Game, complete observed windows:** `crawl_radius_slow_straight_124745`
changed first/high angularVelocity to 1 and reverse to 0.65 on the previous
radius-0.005 setup. Travel 15.079/14.100 m, lateral 0.162/1.397 m, yaw ranges
8.943/14.440 degrees. The reverse path worsened. All follow-ups were skipped.

`uniform_crawl_soft_front_straight_125143` instead used the friction-0.4,
neutral-delay-60 uniform crawl/delta base, enabled soft contact on the front
wheels and added 0.04 m front extraPhysicalRadius. Rear contact remained hard.
Travel 20.391/14.988 m, lateral 0.919/0.516 m and yaw ranges 8.468/8.591 degrees
failed the screen. Full nominal-phase forward pitch reached 4.99 degrees and
height varied 12.5 mm; this is not a stable-contact repair. Native front/rear
physical radii were 0.1135/0.1134 m, yet front runtime centres at rest were
Y42.5604 versus rear Y42.6376. Equal native radii do not establish equal support
or visual placement. Follow-up turning/full throttle were skipped.

The next isolated test reduces torque to 3500 on the radius-0.005,
friction-0.2/neutral-0 base. Earlier torque 3500 failed on a different contact
configuration; usable travel and turning remain required here.

A read-only native geometry probe in that next run recorded physical versus
model-bone centres separately. Hard front physical Y42.5924/42.5927 and bone
Y42.5961/42.5960, rear physical Y42.6376 and bone Y42.6399/42.6398. Nominal
front/rear radii are 0.0761/0.1160 while GetPhysicalRadius returns 0.0785/0.1134.
These are distinct quantities; no unverified collision-margin arithmetic is
promoted to an SDK rule. Probe and raw response are retained in
`crawl_radius_low_torque_straight_125503/physics_geometry.*`.


### Lower torque and heavier wheels rejected (2026-10-05)

**Game, complete observed windows:** on the friction-0.2, neutral-0,
front-radius-0.005 base, `crawl_radius_low_torque_straight_125503` reduced
engine torque 14000 to 3500. Unlike the earlier high-friction torque-3500
trial, this one retained travel: 17.096/12.178 m forward/reverse. It still
failed straightness at 0.746/1.594 m lateral and 8.624/12.017 degree yaw ranges.
Usable low-power drive on this surface is not proof of improved handling.

`crawl_radius_heavy_wheels_straight_125822` restored torque 14000 and instead
tripled wheel masses to front120/rear180 kg (native confirmed), with chassis
1200 kg unchanged. Travel 19.304/13.487 m, lateral 0.807/1.403 m, yaw range
12.840/14.766 degrees: rejected. Both failed screens skipped their turning,
full-throttle and idle follow-ups.

Settled observed-window diagnostics found lower reverse wheel-spin standard
deviation in the heavy-wheel run (front about0.45-0.49, rear0.28-0.36 rad/s),
but higher heading-rate variation and a worse path than the first radius run.
Reducing rotational fluctuations alone did not establish straightness. The
local wheel_yaw_stats.py proxy uses an explicitly unverified 25 mm rolling-
radius addition; its correlation is diagnostic only, not a force measurement
or proof of cause.

Next: all four slot torqueType=full on the original radius base, without
differential locking. It is an SDK enum but absent from the 33-tracked-vehicle
survey; until startup and runtime flags are verified it has no measured effect.
A geometry-scale-only park diagnostic is prepared separately, untested, to
inspect propagation before any coherent size comparison. No size change or
new package has been selected for delivery.


### Native assertions recovered from the engine sandbox (2026-10-05)

The full-torque and scale-only probes both failed startup; neither produced
driving telemetry. The scale run's engine process had window title CRASH.
The full native log was found at the SDK sandbox/xgine/logs/log.txt; rotated
copies live in logs.bakN. The IntegrationStudio stdout was incomplete for
diagnosis. No configuration changes or UI automation were needed to read it.

**Game, invalid diagnostic configurations:** scale2_geometry_probe_park_130527
raised truck_track.cpp(167): rollers shifted along X 0.176106 m, limit 0.001 m.
Its geometry-only scale=2 did not keep physics and visual rollers aligned.
This does not establish how a coherently rescaled model would behave.
crawl_radius_full_torque_straight_130147 raised truck_track.cpp(728):
numActiveRollers is 0. Full wheel torque is therefore unusable in that exact
track configuration, not a successfully tested drive mode.

Full logs and assertion excerpts are preserved under each run's
engine_diagnostics directory with current-snapshot SHA-256 manifests:
scale 966dccc645e06739055f78fc65bb510e6014e98a483e9205e7edd3bd095bfeb7;
full torque 351de026b8a391a92e8a1feccfb43949aa8fcc2badce26f13e04e329dd0efb6c.
No report was submitted. Reproducing the sprung-wheel startup failure with
the engine log visible is the next diagnostic step. Installed r2 and rejected
authoring r4 remain unchanged; no r5 package exists.


### Sprung-wheel crash isolated to the belt configuration (2026-10-05)

`sprung_assert_probe_straight_131923` reproduced the all-sprung startup failure:
native ds_vector_new.hpp(272), invalid index -1 in a vector of length 34.
There was no SSL callstack or object context. Its exact internal origin remains
unidentified; no previous timeout is retroactively assigned this assertion.
Preserved log SHA c5f6b1055b8ce8c7334fab2b2ec510a037b8e95d71ffdb639b2e45d43213ffcb.

The first belt-removal diagnostic, `sprung_without_belt_probe_straight_132331`,
was invalid because PropTruckTrackOutline requires PropTruckTrack. This separate
dependency failure is preserved and is not evidence against suspension.
After also removing the track outline/fresnel/hashed-opacity/phantom/covering
properties, `sprung_without_belt_complete_straight_132619` loaded and drove
with all five inputs. Complete observed forward/reverse paths: 14.291/10.424 m,
lateral 0.475/0.972 m, yaw ranges 10.020/15.851 degrees. The all-sprung wheels
work without the belt properties in this fixture, localizing the startup issue
to the combined track configuration. This deliberately beltless diagnostic
cannot be delivered, and its driving still fails. Native physical radii were
0.0511/0.0910 without the belt versus 0.0735/0.1134 with the original section;
the difference matches section height, without proving collision-margin math.

The isolated bench editor.cfg now enables assertion/native-callstack logging
and prevents crash submission. Its original bytes and before/after hashes are
retained in reports/editor_config_before_assert_logging.cfg and
reports/assert_logging_config.json. Global SDK configuration is unchanged.
Future source snapshots also bind that local config. A front-only compliant
version of the low-friction crawl/radius setup is under test; a default-driven
raised anchor is a separate prepared diagnostic. Neither is a release candidate.


### Front compliance rejected; native discovery failure separated (2026-10-05)

`crawl_radius_front_sprung_straight_132949` reached BENCH_GAME_MODE_READY but
all native control/probe clients failed discovery; the telemetry file is empty.
The native log shows no ap/assert and continued advancing frames. This is an
unmeasured transport failure, not a drive or physics failure. The isolated
assert-logging config was restored byte-for-byte, with restoration receipt in
reports/assert_logging_restore.json. The logging change is not established as
the transport failure's cause; the global SDK config was never modified.

The same vehicle setup on the restored config,
`crawl_front_reconnect_straight_133440`, applied 5/5 controls and produced valid
telemetry. Complete observed forward/reverse: 19.436/14.362 m travel,
0.152/0.676 m lateral, 4.253/9.792 degree yaw ranges. Reverse fails the unchanged
0.5 m gate; turning/full/harsh/idle/park follow-ups were skipped. Front compliance
on the friction-0.2, neutral-0, radius-0.005 crawl base is rejected as a complete
repair. The native unlocked-differential speed-averaging option on the rigid
version is the next isolated trial. No delivery candidate has been selected.


### Rigid anchor failed; averaging torque setting under validation (2026-10-05)

`sprung_driven_anchor_straight_134125` made the two existing diagnostic raised
rigid anchors default-driven instead of passive. It still hit the same native
invalid index -1 / vector length34 assertion. The engine log is preserved at
SHA c218c1f2230384ece8a6bb6291420d9c5fdc1a77ca655d61a52a1a7f3e5fc015;
assert_stop.json records closing only the identity-verified CRASH engine/studio.
This rejects the driven-anchor startup hypothesis for that layout.

`crawl_radius_average_straight_133801` enabled isUnlockDiffAvrVelocity on the
rigid friction-0.2, neutral-0, radius-0.005 crawl setup. Native readback confirmed
avg1, minimum torque0.1. Whole forward/reverse: 19.432/14.489 m, lateral
0.852/0.476 m, yaw range8.153/4.749 degrees. Forward failed; follow-ups skipped.

`crawl_radius_average_full_straight_134351` then changed only
unlockDiffAvrVelocityMinTorque to1 (native confirmed). Its first complete
partial-pedal paths passed the provisional screen: 19.508/14.532 m travel,
0.458/0.415 m lateral, 10.373/6.443 degree yaw ranges. Normal turns applied9/9
inputs and achieved -61.9/+64.3 degrees over0.98/1.05 m. This is a promising
single run, not validated repeatability. Straight capture endpoints00/03 were
visually reviewed: upright body and consistent belt outline; not a complete
idle-sequence or campaign review. Full-throttle, harsh-turn, idle and park
schedules remain in progress. There is no r5 source change or package yet.


### Averaging torque1 rejected at full throttle; contact modifier rejected (2026-10-05)

The promising partial run `crawl_radius_average_full_straight_134351` failed
its sustained full-throttle follow-up: 20.644/15.254 m forward/reverse travel,
2.579/0.522 m lateral deviation, 10.463/5.526 degree yaw ranges, 5/5 controls.
Its acceptable partial paths and turning do not override this failure.
Harsh turns applied9/9 inputs and achieved -74.4/+78.6 degrees (1.82/1.55 m).

Settled observed idle/coast/coast_reverse/final phases applied7/7 inputs and
had maximum endpoint displacement0.570 mm, vertical range0.160 mm, wheel spin
0.035 rad/s. The same-session park applied1/1 and recorded zero displacement,
vertical range and spin at telemetry precision. All four after-idle images
were reviewed: the belt outline stays consistent, body upright, no gross belt
movement visible in those sampled frames. This supports the visual/idle finding
but not continuous-video proof or repaired full-throttle handling. Snapshot
image hashes and review scope are in reports/average_full_visual_review.json.

`crawl_radius_noanti_straight_135333` returned to the rigid radius base with
averaging disabled and switched off wheel anti-tunneling. Native anti0000 was
confirmed. Forward/reverse whole paths: 19.413/14.408 m, lateral0.227/0.734 m,
yaw range7.356/4.561 degrees. Reject reverse; normal/full follow-ups skipped.
The next trial matches reverse gear angularVelocity2/gearRatio3.8 to forward
on that base, with anti-tunneling restored. No new package or source revision
has been produced. Installed r2 SHA was reverified at03:52UTC unchanged.


### Matched gears and stronger lateral grip rejected (2026-10-05)

`crawl_radius_symmetric_straight_135713` matched reverse angularVelocity2 /
gearRatio3.8 to forward. Whole forward/reverse paths were 19.595/20.041 m,
lateral0.512/0.166 m, yaw ranges10.262/5.204 degrees, all5/5 controls.
It misses the unchanged forward0.5 m limit. Normal/full follow-ups skipped.

`crawl_radius_lateral3_straight_140124` used sideways friction multiplier3,
maxVelocity0.1 on the radius-reset base. Whole paths19.631/14.488 m,
lateral0.828/0.051 m, yaw ranges7.991/3.550 degrees;5/5 controls.
Reject forward; normal/full follow-ups skipped. Native logs preserved for both.

The next diagnostic rebuilds all five model assets at twice linear size with
matching wheel dimensions, belt section and COM, retaining mass. This tests
size and inertia together, not a unique solver cause. It is separate from the
production project and has no release status. Installed r2 remains unchanged.


### Coherent double-size diagnostic rejected; control-path distinction (2026-10-05)

Built five native Blender assets separately in scale2_probe, scale1.96 versus
original0.98, same1200 kg body. Compiled wheel-mount names and axes match, all
eight mount positions are twice baseline within3e-8 m. Body COM and wheel/belt
dimensions were doubled; geom.scale remains1. Source, compiler logs and75-file
asset manifest are retained. This changes size and inertia together and is not
a selected appearance change. The first preparation attempt stopped on the
visual-wheel schema; corrected and resumed with explicit dimension guards.

`scale2_probe/runs/scale2_radius_straight_141720` applied5/5 inputs:
whole forward35.434 m / lateral0.214 m / yaw range3.156 degrees;
reverse25.356 m / lateral1.565 m / yaw6.696 degrees. Reject reverse.
Normal turns9/9 achieved -32.0/+32.4 degrees. Full-throttle5/5:
37.676 m / lateral0.491 m / yaw1.392 degrees forward;
27.557 m / lateral1.112 m / yaw3.901 degrees reverse. Reject reverse.
The original close camera crops the larger body; reviewed straight00 shows a
continuous visible belt outline but is not a full-model visual acceptance.
Remaining same-session idle/park measurements are preserved in raw summaries.
Doubling geometry did not establish a handling repair or unique root cause.

SDK source inspection identifies a control-path limitation: the bench Debug
method writes truck.input.pedals and steer directly in DbgUpdateInputs, bypassing
UpdatePedals' LerpFloat(...,truck.pedalsResponsiveness) and UpdateSteering.
The raw-input bench remains useful, but does not test player input smoothing.
The next trial checks whether the existing State input writer persists through
the normal controller. Its success is not assumed. No production sources,
package or installed r2 bytes were changed by the size diagnostic.


### Normal controller works; full launch metric added (2026-10-05)

`r2_state_path_stateprobe_142617` used input_override Method State, with debug
override left disabled on a fresh engine. Three acknowledged requests and a
9m observed forward drive confirm persistence for this native session. The
same-session partial/full schedules applied5/5 each. Original r2 source/native
assets were restored for this baseline; no size change or tuned candidate.

Partial target-pedal windows: forward18.303m/lateral3.545m/yaw25.343deg;
reverse13.185m/1.646m/11.866deg. Full-pedal:20.043m/0.790m/12.467deg and
15.813m/0.251m/10.890deg. These differ from the historical Debug stress runs;
keep control method and achieved speed/gear separate when comparing.

New `stabilityBrakeBounded` includes the complete ramp between observed
handbrake transitions, still requiring a target-pedal seed and straight
steering. It rejects non-straight protocols and adjacent identical brake
phases. Existing measurements are retained. Six new regressions cover launch
kick inclusion, unchanged constant-input behavior, missing target/full-pedal
seeds, ambiguous missing brake telemetry and invalid protocols. All31 bench
tests plus9 vehicle-workflow tests pass. Backups are retained under
reports/metrics_before_brake_windows. This shared runtime change requires fresh
recipe pins for any future release.

The separate brake_bounded_metrics.json baseline reports whole ramps:
partial18.402m/4.447m/28.233deg forward,13.235m/1.507m/11.866deg reverse;
full20.172m/0.404m/12.467deg forward,15.947m/0.402m/10.890deg reverse.
Window-dependent initial headings can make either lateral result larger.
Original summaries remain untouched. Comparison requires both metric windows.

Next is `crawl_radius_pedal001` through State: original dimensions on the
radius-reset diagnostic base, pedalsResponsiveness0.01 rather than0.25.
It keeps the base's one-forward-gear crawl configuration. This is not a
release or restored original-speed claim. Both full-ramp and target-pedal
straight windows must pass the unchanged0.5m absolute limit before follow-ups.


### Gentler throttle rejected; absolute mass comparison pending (2026-10-05)

`crawl_radius_pedal001_straight_143207` applied5/5 State requests.
Target-pedal windows: forward15.158m/lateral0.512m/yaw6.941deg;
reverse11.185m/0.252m/12.031deg. Complete brake-bounded ramps:
forward19.292m/0.150m/6.941deg; reverse14.264m/0.659m/12.031deg.
It fails the unchanged absolute limit in different directions under the two
windows. Normal/full/harsh/idle/park follow-ups were skipped. No release claim.
Native log snapshot13fc2ed98a5718834e61952d0475a55928c6feb6bb9bc2538ebd68c32fdf9d53.

SDK TruckDiffLockType exposes DEFAULT, NONE and ALWAYS. The inspected blueprint
nodes did not provide an automatic steering-dependent differential lock. This
is a limited search result, not proof that no extension route can exist. A
permanent lock's poor steering was already measured and is not a repair.
Wheel radiusOffset and rimRadius default to0 and deformEnable toFalse;
these are not missing rigid-wheel overrides in the tested classes.

The official Game Logic guide warns that low wheel masses can behave
unpredictably, but does not establish a minimum or diagnose WALL-E:
https://roadcraft-modding.prismray.io/truck_modding/mod_editor/bro_files/
The Nodes guide covers visual scripting; it did not establish a heading-lock
implementation: https://roadcraft-modding.prismray.io/scene_components/blueprints/nodes/

The current diagnostic `crawl_radius_mass10` returns to the radius-reset base
with normal0.25 pedal response and scales all masses and engine torque by10.
Geometry and mass/torque ratios stay unchanged. This tests absolute solver/load
sensitivity;14-tonne total weight is not selected for delivery. Still no new
release source/package or installation. Separately, checking the minimal
no-pulse configuration through the now-verified normal controller remains
useful: previous tests of it used the direct Debug override.


### Normal-control mass and minimal-text variants rejected (2026-10-05)

`crawl_radius_mass10_straight_143857` applied5/5 State requests. Target windows
forward19.592m/lateral0.865m/yaw8.777deg and reverse14.356m/0.490m/6.583deg.
Complete brake-bounded ramps:19.594m/0.839m/8.777deg and14.443m/0.494m/6.583deg.
Reject forward; follow-ups skipped. Native log SHA256
cf34e27c2b68bd906c152687edff8a12d9a42e28a30a0660f539802235d819e2.

`nojerk_state_path_straight_144221` tested original-size/gearing/friction
stable_all_nojerk through the normal controller:5/5 requests. Target windows
forward19.146m/0.151m/9.294deg, reverse14.094m/2.101m/15.684deg.
Brake-bounded ramps:19.147m/0.142m/9.294deg, reverse14.175m/2.102m/15.684deg.
Reject reverse; all follow-ups skipped. Native log SHA256
2e1113c0d763f3ff77c8d168389a838d01f7484187e02eaba420b0c6bf6cc640.
Neither absolute mass scaling nor removing engine pulses fixes both directions.

Next structural diagnostic uses independent articulated track frames at original
size, splitting existing model mass400/400/400kg. World wheel mounts and other
four compiled models will be preserved. This changes inertia distribution and
articulation together; overconstraint is a hypothesis, not a proven root cause.
No articulated asset was built at this checkpoint. No production-source/package
or installed change; r2 remains installed, r3/r4 rejected.


### Original-size articulated frames: native valid, first drive rejected (2026-10-05)

Isolated `articulated_probe` surgically reparents all8 wheel/roller bones to two
new identity track frames; compiled world matrices are exactly unchanged. All56
files of the other four model assets remain byte-identical. Model mass is still
1200kg, split400/400/400 across chassis/left/right; wheel masses40/60 unchanged.
Each frame has a +/-5deg transverse hinge, angular damping10 and COM at its pivot
(world Y0.15). Chassis damping100. Assembly internal collision disabled. Elevated
frame bars have23.126mm authored clearance above the rear rigid-wheel envelope;
this is not proof of a private solver margin or visual-idler clearance.

Compiled asset manifest SHA256
31dcd1d803788d1403e993be804f94b567cb31471b528dce2824e41c3eae1d27.
`articulated_initial_straight_145814`:5/5 normal State requests; target windows
forward38.566m/lateral6.041m/yaw22.926deg, reverse13.986m/1.068m/14.099deg.
Brake-bounded forward38.569m/6.034m/22.926deg, reverse14.122m/1.112m/14.099deg.
Reject both directions. It accelerated faster than the earlier single-body
State run, so this is not a matched-speed comparison. All follow-ups skipped.
All three bodies appear in telemetry at400kg each. Initial parked3-10s samples
show0 recorded displacement/height range for each; all four contacts present.
This parked result does not prove unbraked idle stability. Articulation changes
inertia distribution too; it is not an isolated proof about overconstraint.
Native log49ba98219d19fedc3cc923bb43240386ebe90dccf22ac4a483dbee2fb1158d99,
no recorded assertion. One captured side image was reviewed: belt continuous,
full model visible; no sequence or campaign validation. Review pins are local.

Next run applies the existing crawl_radius_reset settings to this same rig to
remove automatic upshifting as a confound. This is still diagnostic, not a
selected package. Installed r2 and production r4 sources remain unchanged.


### Articulation rejected at crawl speed; alternate contact exits (2026-10-05)

`articulated_probe/runs/articulated_crawl_straight_150229`:5/5 State requests.
Target forward19.993m/lateral3.487m/yaw16.909deg, reverse14.549m/0.966m/5.150deg.
Brake-bounded19.996m/3.476m/16.909deg and14.594m/0.977m/5.190deg. Both directions
fail; all follow-ups skipped. All three bodies remained still at initial parked
3-10s sampling, and all wheels reported ground contact. Engine log SHA256
282570d19fbccfc4db3eed0b5480071ecc8c9955b686a5868a782fda2231205f.
The split-frame design is rejected; neither increased speed nor frame settling
explains away its measured drift.198 completed schedules, no passing repair.

`crawl_radius_fake_contact_straight_150624` returned to original geometry and
enabled global useFakeWheels on crawl_radius_reset. It exited before usable
readiness/telemetry. The live engine log was rotated into logs.bak1;
preserved SHA6394cb6e7ecbcc7eecec7b325a935bed16e5e2bc7c333cbf655f522dad44f220.
It ends during actor initialization without an assertion or useful stack. The
studio printed a readiness marker while skipping its delay and exiting, which
the launcher correctly rejected. No exact engine cause is established. Do not
rerun this mode without new evidence. SDK PropTruck.useFakeWheels defaultsFalse;
per-track fakeWheelIds is a separate mechanism. No production/install change.

The original-size single-body crawl_radius_reset has direct Debug evidence,
but normal State controls have only been measured with additional mass or
pedal-response changes. Measure the unchanged crawl variant through State to
complete that comparison; retain all earlier direct-input failures.


### Normal controller crawl suite provisionally passes; repeats pending (2026-10-05)

`radius_state_path_straight_151004` uses unchanged original-size single-body
crawl_radius_reset through State. Main5/5 target windows: forward19.374m,
lateral0.198m,yaw8.304deg; reverse14.570m,0.474m,5.238deg. Brake-bounded:
19.375m/0.174m/8.304deg and14.647m/0.467m/5.238deg. Both also satisfy the
existing partial-pedal baseline-relative ratios against the matching r2 State
baseline, not the direct Debug baseline.

Normal9/9 turns-65.6/+60.1deg. Full-pedal5/5 target: forward20.547m/0.403m/
3.077deg; reverse15.355m/0.487m/7.330deg. Brake-bounded20.547m/0.354m/3.077deg
and15.478m/0.432m/7.330deg. Harsh9/9 turns-78.7/+74.4deg. Idle7/7:
observed settled maximum displacement2.094mm, height range1.4mm, spin0.172rad/s;
handbrake-off stationary idle and final parked phases recorded0 movement.
Park1/1 recorded0 displacement/height/spin. This uses maximum displacement
within the settled observed window, not just endpoint distance.

All21 provisional checks pass in `provisional_suite_check.json`, including
both target-input and complete ramp paths, all inputs, both turn signs, idle
and park. This is ONE source-fixture session, not release validation. Earlier
Debug repeat/full failures remain valid stress evidence. At about4-4.5km/h this
is a slow crawler; no terrain/campaign generalization or owner acceptance.
The native log is pinned at
c382387655498b1845416639381c975031a53cbaec2c5d16d630b1392edc28a7.
Eight selected images were actually reviewed and pinned in
reports/radius_state_visual_review.json: consistent belt outline and upright
body; shadows limit tread detail and sampled stills do not cover every frame.

A fresh radius_state_repeat1 session is testing partial and full pedal before
any source/package promotion. No r5 sources/package or installation yet.
`reports/controller_comparison.json` keeps all completed State schedules and
their raw/snapshot hashes separate from direct-input stress tests.


### Normal-control crawl repeat rejected; slot-order comparison (2026-10-05)

The fresh `radius_state_repeat1_straight_151935` applied5/5 State requests.
Target forward19.417m/lateral0.223m/yaw7.694deg; reverse14.421m/0.550m/4.808deg.
Complete ramps19.420m/0.182m/7.694deg and14.509m/0.500m/4.808deg (unrounded
reverse ramp0.499625890818263m). Target-window reverse exceeds the unchanged0.5m limit;
full-pedal follow-up skipped. The first suite pass remains recorded but cannot
establish a repeatable repair. No candidate sources/package were prepared.
Engine log93384b27102a8c017891e540db53dc9f2010028dc2dca7c2a9b968f4a4217653.

`crawl_radius_interleaved` compares only wheel enumeration. The original
L-front/L-rear/R-front/R-rear order becomes L-front/R-front/L-rear/R-rear;
track wheelIds are remapped to[0,2] and[1,3]. Reversing that mapping gives
semantic equality to the first State run, with every other snapshot resource
byte-identical, recorded in reports/interleaved_static_equivalence.json.
Retail side-grouped layouts are valid; this is a test of solver sensitivity on
this small rig, not a claim that original slot order is incorrect.205 schedules
complete before this comparison. r2 installed, r3/r4 rejected, no r5.


### Interleaving rejected; matched reverse gearing under normal controls (2026-10-05)

`crawl_radius_interleaved_straight_152320` applied5/5 State requests. Target
forward19.533m/lateral0.184m/yaw7.433deg, reverse14.462m/1.716m/10.846deg.
Brake-bounded19.536m/0.167m/7.433deg and14.500m/1.719m/10.846deg. Reject
reverse; all follow-ups skipped. Native readback confirms wheel mass order
40/40/60/60. The preserved engine log is
6d9101fb7f4de690bf519fd48939bdffaf935ff05e3fa0016b8b705214f752ed.
One reordered run changed behavior but does not establish a universal solver
ordering rule or fix. Original side-grouped order is retained.

The next original-rig State diagnostic is `crawl_radius_symmetric`: reverse
angularVelocity2,gearRatio3.8, matching the first forward crawl gear. Its earlier
Debug run had forward0.512m/reverse0.166m and was rejected. The normal controller
comparison is distinct and cannot erase that stress failure. It may clarify
the remaining reverse sensitivity at matched crawl speeds.206 schedules complete
before this test; no r5 source/package or installed change.


### Matched reverse gearing rejected through State (2026-10-05)

`symmetric_state_path_straight_152651`:5/5 inputs, original slot order.
Target forward19.400m/lateral0.195m/yaw5.982deg; reverse19.827m/1.919m/9.108deg.
Brake-bounded19.402m/0.163m/5.982deg and19.910m/2.211m/9.448deg. Reverse fails;
all follow-ups skipped. Native log
948d376d8033d4c1f4b24435c78c17ab3c224845400b10fa030659d18de693c1.
Matched speed does not fix the reverse behavior.207 completed schedules before
the next diagnostic. No r5 sources/package or installation.

`crawl_radius_substance0` returns to original reverse gearing and isolates
substanceFriction0 on physical wheels and default/asphalt material entries,
retaining body friction0.2, radius adjustment0.005 and all other crawl settings.
The older friction0.4/no-radius direct-input nosub trial improved reverse but
failed forward; this specific combination and normal State input path remain
unverified. No statement about general terrain behavior is established.


### Axle contact resistance isolation, normal controller (2026-10-05)

`crawl_radius_substance0_straight_153125` completed six schedules: main and
full straight 5/5, normal/harsh 9/9, idle 7/7, park 1/1. All four wheels
read friction0.2/substance0. Target partial forward19.4812m/lateral0.3400m/
yaw10.7187deg; reverse14.5029m/0.0287m/4.0442deg. Brake-bounded partial
19.4834m/0.3799m/10.7187deg and14.5463m/0.0288m/4.0442deg.
Normal turns -58.0/+59.8deg and harsh -77.7/+82.9deg passed their screens.
Full forward failed: target20.7558m/1.4625m/7.8992deg, brake-bounded
20.7559m/1.4647m/7.8992deg. Full reverse15.0404m/0.0643m/2.7438deg
(brake-bounded15.1471m/0.0541m/2.7438deg). Provisional suite check rejected
two full-forward checks. Settled coast maximum displacement5.828mm, height
range1.0mm, peak wheel spin0.262rad/s; parked movement zero. Captures retained
but not visually reviewed. Native log2533deb8748f593007dd9f011dc261eb0f05d8931f933ac3d2845303be0aa86c.

`crawl_radius_rear_substance0_straight_154105` removed resistance only from
the big/rear wheels. Native readback confirmed front/rear substance1/0.
5/5 inputs, target forward21.0539m/1.0428m/8.4208deg and reverse
14.3298m/0.1835m/4.5341deg; brake-bounded21.0567m/0.9662m/8.4208deg
and14.4002m/0.1853m/4.5341deg. Rejected forward; all five optional
follow-ups skipped.214 completed native schedules. Resistance is not an
established sole cause. No r5 authoring/package or installation.

The local runner now supports --screen-followups, stopping subsequent
optional schedules when a follow-up sustained straight check fails. This
guard has passed syntax inspection but has not yet been exercised natively;
the rear-only run stopped at the existing main screen.


### Front-only resistance rejected at full pedal (2026-10-05)

`crawl_radius_front_substance0_straight_155054`, State: main5/5, normal9/9,
full5/5. Native readback confirmed front/rear substance0/1 and friction0.2.
Target partial forward19.8332m/0.2645m/10.2488deg, reverse14.6115m/0.2319m/
4.4808deg; brake-bounded19.8355m/0.2029m/10.2488deg and14.6561m/0.2129m/
4.4808deg. Normal turns -66.4/+53.5deg. Full forward20.1236m/2.5518m/
16.9994deg and reverse14.5947m/0.8800m/14.9275deg; brake-bounded
20.1251m/2.5270m/16.9994deg and14.7221m/0.9291m/14.9275deg. Rejected.
The new follow-up screen executed and skipped harsh/idle/park after this
failure, retaining the failed full run and its captures.217 completed schedules.
No production r5 source, package or installation.

SDK source inspection found public RigidBody.SetAngularVelocity and
ApplyAngularImpulse methods in physics/rigid_body.ssl. This corrects any
inference from the absent blueprint node that native angular control is
impossible. Shipped scripts are compiled .sslbin; no supported custom-script
compilation/package route has been verified with the supplied tools. No
runtime heading assist has been implemented or tested. A same-surface retail
crawler control is being prepared; it cannot change the recorded WALL-E gates.


### Stock crawler control on the same terrain (2026-10-05)

`retail_control/runs/stock_tc305_straight_160002` loads the stock EPEC TC-305
prefab on the unchanged terrain with normal State controls. Only the control
fixture's prefab reference/spawn clearance differ. Native telemetry confirms
45,000kg chassis,14 wheels, four real physical radii0.515m. Stock class member
SHA7eae0075a9fcde400e817528141d20771c8badf632cb99eb3e400d3a4f3e6a33;
preparation.json preserves prefab/source and scene pins. No stock package edits.

Straight5/5 target forward61.448m/lateral0.950m/yaw1.644deg, reverse47.791m/
0.781m/1.594deg; brake-bounded61.448m/0.950m/1.644deg and47.803m/0.780m/
1.594deg. Normal9/9 turns -74.2/+74.2deg. Full5/5 forward91.194m/1.055m/
2.263deg, reverse57.720m/0.316m/0.482deg. Full brake-bounded forward1.046m
lateral, reverse0.316m. Native logd1a9e67799f7c3b3c07b04b90d2f431c8cdb230197caaa6ccc43696c79ffe71f;
no assertions. This is numerical control evidence, without visual review.

For an explicitly separate first20m comparison, partial forward20.113m/
0.131m/0.736deg and reverse20.179m/0.166m/0.813deg; full20.369m/0.107m/
0.467deg and20.218m/0.056m/0.237deg. Full windows remain above and in
retail_control/comparison.json; these shortened control windows must never
replace WALL-E's whole-path release gate. Different size, support layout,
mass and speed prevent unique causal attribution, but the control does not
support blaming WALL-E's larger heading swings solely on the test terrain.

217 WALL-E schedules plus3 stock-control schedules are now complete.
`equal_roll_crawl_probe` is the next isolated normal-controller diagnostic:
equal front/rear physical radius0.0761 with extra radius0.005 and lowered rear
centres, retaining40/60kg wheel masses and crawl contact settings. It differs
from the earlier rejected high-friction equal-roll probe. The temporary
rear visual is known to have an orientation mismatch and upper rollers are
omitted; this exact form is not eligible for release, regardless of driving.
No production source/package/install change.


### Equal physical rolling radii rejected at full pedal (2026-10-05)

`equal_roll_crawl_probe_straight_160636` confirmed four native physical
radii0.0785m and original40/60kg wheel masses. State partial5/5 target
18.0899m/0.4402m/9.9318deg forward,13.6334m/0.2404m/4.8998deg reverse;
brake-bounded18.0977m/0.4359m/9.9318deg and13.6980m/0.1830m/4.8998deg.
Normal9/9 turns -67.2/+61.8deg. Full5/5 failed both directions: target
18.6163m/2.1703m/12.7723deg and13.5227m/1.3103m/11.7455deg;
brake-bounded18.6196m/2.1827m/12.8107deg and13.6231m/1.3036m/11.7455deg.
Native logdaaf0094059f5e8144862d5cbddc9ff0a75bedc11721d737835b93d906da5893,
no assertions. Captures retained without a visual review; its known incomplete
visual layout was never delivery eligible. Equal radii on this contact setup
do not establish a repair.220 WALL-E schedules +3 stock controls complete.

The next `crawl_two_raised_drives` layout retains original visual/ground
wheel dimensions, puts the four ground wheels in sprung track fakeWheelIds,
and registers four small hidden rigid rollers at the two existing upper
roller mounts per side. There are now two wheelIds per track, not the zero/
one of earlier all-ground-support trials. Their class/per-truck/library
registrations and dependencies are included. Global useFakeWheels remains
false. Ground axle min-0.008/max0.006/height0.006/strength1/damping0.55;
upper radii0.03, mass40kg each, adding160kg. These changes are a structural
diagnostic, not an identified cause or validated design. Prior off-ground
driven-wheel traction failures remain relevant; no outcome is assumed.
No production r5 source/package/install.


### Two rigid upper anchors: outline startup repaired, traction inadequate (2026-10-05)

`crawl_two_raised_drives_straight_161304` asserted before Play:
truck_track.cpp(322), "Not enough track segments created". Four sprung ground
fakes and two rigid hidden upper wheelIds per side did not provide a complete
rendered envelope. Log ab5f2d5c8edc97771de0cb999e6e9d659b37178f4a6761ca0a13a77e42cd1d8e
and verified owned-process stop are preserved. No driving result exists.

`crawl_two_raised_outline_straight_161730` adds separate front/big visual
descriptors, registered in BOTH wheel tables with dependency links, and removes
the physical ground wheels' duplicate geometry. It reached Play with eight
wheels: four sprung ground contacts and four rigid upper wheels airborne.
Original ground masses40/60kg; upper wheels40kg/radius0.03m each add160kg.
Native front/rear radii0.0785/0.1134m, upper0.0274m; ground travel about10mm.
State5/5 target paths7.2060m/0.0831m/10.9930deg forward and
3.9867m/0.0554m/5.7352deg reverse; brake-bounded7.2084m/0.0914m/10.9930deg
and4.0044m/0.0558m/5.7352deg. Both fail the unchanged >10m travel gate.
Small lateral motion over these short paths is not a handling fix. Normal/full
follow-ups were skipped. Four captures retained, not visually reviewed. Log
d9e444330afee0013f1739166e87e12ca469888ecdf45b8aaa4b55372ba147ff,
no assertions.221 WALL-E completed schedules plus3 stock controls.

Next isolate upper-wheel drive with torqueType none on slots4-7, keeping
the four ground defaults and complete envelope. A separate four-real-rollers
per-side layout is prepared with two rigid upper anchors and two sprung ground
wheels; it has not yet run. Earlier one-anchor/all-sprung failures do not prove
this two-anchor layout invalid. Both are diagnostics only. No r5 source,
package or install; r2 remains installed.


### Passive upper rollers recover travel but wander; real-wheel spring layout asserts (2026-10-05)

`crawl_two_raised_passive_straight_162640` changed only upper slots4-7 to
torqueType none from the preceding complete-outline layout. State5/5 target
paths19.7082m/2.8559m/15.5526deg forward and14.1751m/1.2365m/9.3957deg
reverse; brake-bounded19.7100m/2.7962m/15.5526deg and
14.2143m/1.1634m/9.3957deg. All follow-ups skipped. Relative to the 7.206/3.987m
driven-upper run, passive upper rollers recovered travel on this same layout,
but lateral wandering rejects it. It does not diagnose the original four-wheel
mod. Captures retained without visual review. Log
284b6a93ea1f0d56dafcab1a1fdd886b22251040d01d0b20d92cf6bff21be0cf,
no assertions.222 completed WALL-E schedules plus3 stock controls.

`crawl_four_real_per_side_straight_163007` put both sprung ground wheels and
both rigid upper rollers in wheelIds per side, with no fake IDs, retaining
original wheel geometry. It asserted before Play: invalid index -1, length34
in ds_vector_new.hpp(272). Log
c51bda757804f6530d5b03d68a5314ee9d91b30750b1e3ce60df21b087c7fe2b;
assert_stop.json verifies only this crashed engine/studio were closed. This
distinct two-anchor real-wheel layout did not clear the earlier startup fault.

An isolated follow-up reverts only track tensions10/10 to native defaults
0.04/0.16, testing an interaction rather than rerunning the failed configuration.
No result yet. A rear-only drive trial on the low-friction crawl/radius base is
prepared but untested; earlier rear-only trials used high friction, original
gears and torque7000. No r5 source/package/install and no selected repair.


### Native tension control and single-axle drive rejected (2026-10-05)

`crawl_four_real_low_tension_straight_163442` reverted only tensions10/10 to
0.04/0.16 on the four-real-rollers-per-track layout. It still asserted before
Play with invalid index -1/length34. Log
5f4dbffba2518c3b89a4c5ff6f2110735257cad7492f03c28fce0d76ec19adaf,
verified owned-process stop retained. High tension is not required for this
startup failure. Shipped Bowhead and ATM53 classes group several longitudinally
separated sprung wheels into one axle entry; the speculative grouping-only
explanation is unsupported. No extra axle-splitting experiment was run.

`crawl_rear_drive_only_straight_163729` retained crawl/radius/friction0.2 and
torque14000, changing only front torqueType to none. State5/5 target paths:
22.7697m/0.5642m/10.7805deg forward;16.9441m/0.9657m/7.1724deg reverse.
Brake-bounded22.7712m/0.6050m/10.7805deg and16.9721m/0.9408m/7.1724deg.
Reject both paths. Follow-ups skipped. Log
7f750b715229a17a4fe3154eb00a57c3f8fea1db33c8af628aba862737034341.

Opposite `crawl_front_drive_only_straight_164100` State5/5 target partial:
15.4848m/0.4278m/13.3652deg and13.2282m/0.4485m/5.4941deg;
brake-bounded15.4879m/0.4534m/13.3652deg and13.2520m/0.4900m/5.6676deg.
It passed the partial lateral screen, but forward yaw exceeds the required
50% reduction versus matched r2. Normal9/9 turns were only -7.6/+8.4deg,
below20deg each: independently rejected as a usable vehicle. Full5/5 target
18.6965m/0.3247m/4.7150deg and14.1489m/0.5404m/3.4643deg;
brake-bounded18.6965m/0.3247m/4.7150deg and14.1902m/0.4933m/3.4643deg.
Full reverse target also exceeds0.5m. Log
e5e227a5577cb7914f6e141acdcc2e8b3fcca32d1f80304f04746288ec8b526b.
No assertions in either driving test. Only front-drive straight00 was viewed:
upright complete model and continuous dark belt; no sequence acceptance.

226 WALL-E schedules plus3 stock controls completed. The runner now also screens
normal/harsh turns against the existing opposite-sign20/40deg gates when
--screen-followups is used, so failed steering will skip later optional work.
New native validation of this additional guard remains pending. Aggregate last
refresh222 schedules/32 State schedules predates these final drive results.

Next normal-controller diagnostic keeps four driven wheels and original size,
sets pedalsResponsiveness0.1, intermediate between near-instant0.25 and the
previously rejected long0.01 ramp. All other crawl/radius settings and the whole
target/brake-bounded gates remain unchanged. No r5 source/package/install.


### Contact/ramp failures and native numeric writer defect (2026-10-05)

`crawl_radius_pedal010_straight_164758` moderate pedal response0.1, State5/5:
target forward19.4605m/0.4689m/9.4145deg, reverse14.3882m/1.7472m/9.9241deg;
brake-bounded19.5647m/0.2051m/9.4145deg and14.6316m/2.1267m/11.2619deg.
Reverse failed and all follow-ups skipped. Log
f0976bc14d69518fbc4d840c0df7a33e8b66ceebd00ecc31300cd0203acadeb7.
`crawl_thin_contacts_straight_165209` isolated physical widths0.02m instead
of0.1854, original radii/masses/models; State5/5 target19.5813m/1.4075m/7.8023deg
and14.4057m/0.1212m/3.9023deg; brake-bounded19.5870m/1.4718m/7.8023deg and
14.4975m/0.1385m/3.9023deg. Forward failed; follow-ups skipped. Native readback
confirmed all widths0.02. Log2cf392689c707b1d952f593ec736923637ad6054a5fb3be6682c06fa8cdaf738.
No assertions; captures not reviewed.228 completed WALL-E schedules before
the next motor-limit suite, plus3 stock controls.

`crawl_delta00002_straight_165627` lowered maxDeltaAngVel by10 but its generated
scientific notation2e-05 failed before Play: unsupported psARRAY in
ssl_desc.cpp(280). Log1b3143e4c3aa504cf9e231b7e63aa941be39897c4d6d17c4f4a65501a4cab67d.
`crawl_delta00002_decimal_straight_170306` replaced ONLY that token with0.00002
and reached Play. Snapshot gameplay-file comparison proves class-only change,
Python semantic equality, and exact textual substitution. The original result
is a loader failure, not a motor behavior result.

Shared ps_format.dumps now expands finite float representations into fixed
decimal notation without precision loss, preserves float types and signed zero,
and rejects non-finite values. Historical exponent notation remains readable.
The existing authoring paths already call this writer. Native comparison and
before/after writer hashes are in reports/ps_decimal_native.json; backup in
reports/ps_format_before_decimal.py.5 numeric tests,26 vehicle-library tests and
9 vehicle-workflow tests pass. Integrated into library/build-pipeline.md.
New recipes must be pinned after the shared-runtime change.

The decimal motor-limit suite has so far passed partial5/5 target
19.8445m/0.4038m/10.9196deg and14.4647m/0.1553m/3.1284deg;
brake-bounded19.8458m/0.4600m/10.9196deg and14.5106m/0.1679m/3.1284deg.
Normal9/9 turns -55.9/+63.2deg; the new follow-up turn guard passed natively.
Full/harsh/idle/park and repeatability remain pending. No release selected.

Separate capability investigation: supplied ModEditor binary contains native
SSL compiler and BinaryModulesGenEnabled option; SDK config sets generation
false and UseBinarySsl true. Isolated ssl_probe contains a harmless new marker
class and resource descriptor. module_probe_park_170024 reached Play with local
generation enabled, but LoadSSLModule returned false and class lookup failed.
No telemetry schedule completed, no new binary found under this probe, and no
heading controller implemented. Logc6a247657480ba4f098879b332360293aa334f09baee13316d6cc724b97c2c38.
Enabling source loading is prepared as a distinct follow-up, not yet launched.
This corrects only the earlier absence of a discovered compiler route; portable
custom-controller packaging is still unverified. No r5 source/package/install.


### Decimal motor limit rejected; SSL resource prerequisite (2026-10-05)

Completion of crawl_delta00002_decimal_straight_170306: the full-throttle
State schedule applied5/5 inputs but failed whole-target lateral checks:
forward20.7356m/2.5858m/12.0304deg, reverse15.3344m/0.5163m/5.6040deg.
Brake-bounded20.7387m/2.6210m/12.0304deg and15.4358m/0.4635m/5.6040deg.
Harsh/idle/park skipped. This supersedes checkpoint52's pending result:
the partial/normal passes do not qualify this candidate. No fresh repeat or
release selected. Log5cfa60d02b74ff862836246f6c704e71a7d29a5ffc9de937d0d44a02c4ddd5f0;
no assertion; captures unreviewed.231 completed WALL-E schedules plus3 stock
control schedules. The separate shared fixed-decimal serializer fix remains
supported by exact native-loading A/B evidence and40 passing focused tests.

SSL source-loading probe module_probe_park_171049 reached Play with isolated
UseBinarySsl=false and BinaryModulesGenEnabled=true, but LoadSSLModule alone
again returned false and marker class lookup failed. No driving schedule ran.
Log994b517efbb31b025faf9c724a14b7829159bc9226230cf7916d6fbaf42d2885; no assertion.
SDK source ssl/autotest/global_autotest.ssl and
ssl/editor/game_editor/game_editor_sequence.ssl load the module RESOURCE TAG
before LoadSSLModule. The two previous capability probes omitted that
prerequisite, so neither establishes that source compilation is unavailable.
The next distinct capability test adds LoadInitialResourceTag for the exact
marker descriptor. Still no heading assist implemented, binary produced,
portable script route established, r5 source/package or install.


### Native source module success and binary-loading blocker (2026-10-05)

Isolated SSL marker module_probe_park_171828 reached native Play, then explicit
LoadInitialResourceTag returned WALLE_RESOURCE_RETURNED, LoadSSLModule returned
true, and new WalleStabilityProbe().Marker() returned WALLE_SSL_SOURCE_PROBE_V1.
The original24s park then completed220 samples with stationary physical rest.
This is a capability schedule, excluded from WALL-E handling counts. Source
mode/local generation settings and marker/resource hashes are preserved in the
run source_control.json and preparation_source_resource_success.json.
Logf624cb986efd8bb0bce88e81dfa7f1c605756f097c44b4ffce96c153c5e96014;
no assertion. No compiled module found in this probe or SDK sandbox.

module_probe_binary_park_172323 restored local UseBinarySsl=true. Native readback
confirmed BINARY_GEN=1 BINARY_LOAD=1. The resource-load call asserted in
res_manager.cpp(514): missing res://ssl/mods/walle_stability_probe_debug.sslbin.
No marker or driving schedule completed. Log
bed9a179b35b8a1ee7c0284db2fb98bb70b7ea93830064e200a5187016442b27.
Owned editor closed by runner cleanup. The source compiler exists and works,
but no reusable compiled output or package-ready controller path is established.
Do not ship editor-only injection or globally change script-loading settings.

Separate longtrack_probe compiled a geometric diagnostic: front/back running
gear mount Z positions and track-frame visual length doubled, wheel circles,
body dimensions, collision, masses, track section and crawl_radius_reset tuning
retained. All8 compiled wheel/roller mount positions match intended transforms,
orientations and node names match.67 asset files pinned. This changes visible
track proportions and is diagnostic only; the State suite is now pending.
Its Blender process omitted explicit Python failure exit initially, but produced
and verified the expected saved blend, rig report and compiled TPL. The local
preparation helper is corrected to --python-exit-code1 for future use.

Aggregates refreshed:231 completed WALL-E schedules,41 State schedules, zero
ambiguous observed phases, plus3 separate stock controls and1 SSL marker park.
No r5 source/package/install or accepted candidate.


### Longer footprint still misses full-throttle straightness (2026-10-05)

longtrack_probe/runs/longtrack_state_straight_172853 completed3 State schedules.
Partial5/5 target forward19.2018m/0.2664m/6.3069deg and reverse
14.2080m/0.3325m/2.4983deg; brake-bounded19.2046m/0.2599m/6.3069deg and
14.2415m/0.4322m/2.6130deg. Normal9/9 turns-62.1/+61.2deg passed.
Full5/5 target forward20.7677m/0.7014m/3.0374deg and reverse
15.1392m/0.1837m/2.4938deg; brake-bounded20.7708m/0.6892m/3.0374deg and
15.2793m/0.1262m/2.4938deg. Forward failed, so harsh/idle/park skipped.
No captures requested in this suite; no visual acceptance. Log
4f4f1329e8729ad97aa3b67c77bd79b56d144a9bcb721ac5872e6f17e385770c; no assertion.
This geometry/tuning is rejected. Lower yaw in one session does not establish
repeatability or prove the short footprint as the sole root cause.

Next isolated longtrack_friction04 variant changes only body/default/asphalt
wheel friction0.2 to0.4 on this same longer geometry. It restores from the
longtrack pristine snapshot; masses, radii, track dimensions and control tuning
stay unchanged. State suite with captures is active, not a selected candidate.

The local follow-up turn guard introduced in checkpoint52 used pivot+/- keys
for both schedules. Normal uses those names, but harsh uses lock+/-. Fixed
the harsh lookup and verified names against actual schedule schemas. No prior
candidate reached that new harsh guard, so this did not reject a measured
passing harsh turn. Existing recorded physical turn metrics remain intact.
The completed longer-footprint suite stopped at full throttle before that guard.

234 completed WALL-E schedules/44 State, plus3 stock controls and1 separate
SSL marker park. Aggregation helpers now include the separate longtrack root.
No r5 source/package/install and no accepted repair.


### Longer footprint/friction0.4 provisional suite pass (2026-10-05)

longtrack_friction04_straight_173541 completed all6 State schedules and passed
all21 checks in provisional_suite_check.json, still requiring fresh exact-package
replays and visual completion. Native wheel readback confirmed0.4 friction.
Partial5/5 target forward19.0427m/0.2539m/6.5731deg and reverse
14.1814m/0.1260m/4.1491deg; brake-bounded19.0454m/0.2574m/6.5731deg and
14.2104m/0.1033m/4.1491deg. These pass the matched original-r2 State relative
ratio/yaw criteria as well as absolute whole-path limits.
Full5/5 target forward20.4545m/0.4606m/2.1814deg and reverse
15.1058m/0.2744m/2.5502deg; brake-bounded20.4594m/0.4173m/2.1814deg and
15.2003m/0.2616m/2.5502deg. Normal9/9 turns-72.1/+68.9deg; harsh9/9
turns-86.0/+82.9deg. Corrected harsh guard passed natively.
Idle7/7 maximum settled displacement0.061mm, height range0.060mm, spin0.002rad/s;
park1/1 reported zero at telemetry precision. Four after-idle frames reviewed:
same belt outline, upright robot; shadow limits underside detail. Straight00
and park00 also viewed. Geometry/visual completion remains pending because of
the changed track proportions. reports/longtrack_first_visual_review.json pins
these images and limits. Log6932057c44d3dd916a06634f2b619208e0829fba3bb7a19aed008fb6ba5f2658;
no assertion. This is one promising source-fixture session, not a release.

Fresh unchanged longtrack_friction04_repeat1 session is running partial,
normal and full schedules. Do not prepare or install a successor based only
on this first pass.240 completed WALL-E schedules/50 State, plus3 stock controls
and1 SSL marker park. No r5 source/package/install; r2 still installed.


### Longer-track first pass fails its fresh full-speed repeat (2026-10-05)

longtrack_friction04_repeat1_straight_174526 applied5/5 partial controls:
target forward19.3267m/0.2535m/7.2683deg, reverse14.2429m/0.0808m/2.1811deg;
brake-bounded19.3307m/0.2541m/7.2683deg and14.2917m/0.1209m/2.1811deg.
Normal9/9 turns-68.9/+67.5deg. These pass.
Full5/5 target forward20.6434m/0.5617m/4.4459deg, reverse
15.0356m/0.4406m/3.0765deg; brake-bounded20.6434m/0.5617m/4.4459deg and
15.1809m/0.4173m/3.0765deg. Forward exceeds the unchanged0.5m limit;
configuration rejected, not rerun for a lucky pass. Reports/longtrack_repeatability.json
verifies identical10 gameplay snapshot files and asset manifest between sessions
and binds the failed raw telemetry. Log
a90927259b274dc0bffc5e21c5552a61fd7d0e63d88dd6fa3b61c2ed5a88ff5e; no assertion.
Repeat captures exist but have not been reviewed. No release was prepared.

Distinct follow-up longtrack_friction04_capped retains geometry, masses,
friction and steering; only forward/high angular velocity2->1.5 and reverse
0.75->0.65 change. Its usefulness is conditional on retaining more than10m
travel per sustained path, the same lateral/yaw gates, and full turn/rest checks.
It is running the full State suite. Final park, if reached, adds opposite-side,
front and rear native views via snapshotted capture_geometry.py; camera changes
occur after telemetry, with lighting/handling untouched. The separately prepared
run_longtrack_visual_review.py remains unexecuted.

243 completed WALL-E schedules/53 State, plus3 stock controls and1 separate
SSL marker park. No r5 source/package/install; installed r2 unchanged.


### Lower-speed longer-track candidate also fails repeatability (2026-10-05)

longtrack_friction04_capped_straight_175334 passed all21 provisional checks:
partial target forward16.9372m/0.2458m/3.7725deg, reverse13.6116m/0.0495m/
0.8887deg; brake paths16.9403m/0.2418m and13.6770m/0.0198m.
Full target18.2773m/0.2643m/2.9529deg and14.7737m/0.4843m/3.8520deg;
brake18.2831m/0.2599m and14.9063m/0.4151m. Normal-72.7/+65.2deg,
harsh-91.1/+92.2deg; all inputs applied. Settled idle max displacement3.623mm,
height0.040mm; park zero at telemetry precision. Log
3a502ccb1050212e299c991652d23f0bae0507bff07003565408474e4f4436e3, no assertion.

Fresh same-source/asset longtrack_friction04_capped_repeat1_straight_180451
applied5/5 partial controls, forward16.6418m/0.2624m/5.3560deg and reverse
13.8280m/0.4883m/3.8588deg. Complete brake-bounded reverse13.8793m/0.5029m
fails the unchanged0.5m limit; normal/full skipped. Configuration rejected,
not rerun for another chance. Log eac1660098675dd484b3f88520c548ae43abe98b918e1397ce0ff2edd33cb998.
reports/longtrack_capped_repeatability.json verifies exact10 gameplay files,
model asset manifest equality and pins raw failure plus the reviewed images.
One earlier mislabeled invocation failed before native startup with ValueError;
it is not a driving result.

Opposite-side/front/rear geometry images were captured after final park. The
right low view exposes an apparent loose lower component; it cannot yet be
assigned to animated belt versus static frame. Idle00/03 silhouettes agree,
but this does not grant visual acceptance. Blender's read-only mesh audit found
static frame components as low as0.0231m and a correctly bounded tread shoe;
it does not resolve the native lower-belt appearance. A dedicated native park
and matched-camera mesh visibility isolation is running. Changes are diagnostic,
not permanent hiding of geometry. No r5 authoring/package/install.

250 completed WALL-E schedules/60 State, plus3 stock controls and1 separate
SSL marker park before the additional geometry-only park.


### Size hypothesis and native geometry isolation (2026-10-05)

The owner asked whether the repair is impossible because of size. No such
conclusion is supported. Small dimensions remain a sensitivity hypothesis;
physical rest, useful turns and improved individual paths have been measured.

longtrack_geometry_park_180915 completed a separate24s native park, followed
by opposite-side/front/rear views and matched low-side whole/no-frame/
running-gear/restored views. Hiding the static frame removes much of the
apparent central bunching; the lower animated belt remains partly obscured
by rendered ground. No broken-loop conclusion or complete visual acceptance.
Visibility restored, physics unchanged; log959d3b30c7bd87a2bff9993927955d8e3b484c59ce77a56b349e53fe1568c03c.
reports/longtrack_visibility_isolation.json pins all4 reviewed isolation images.

The existing coherent double-size model was tested with State for the first
time: scale2_normal_controls_straight_181341. Partial5/5 forward35.1593m/
0.2006m/4.3799deg, reverse25.0252m/0.4417m/4.3571deg; brake35.1593m/
0.2006m and25.0501m/0.4398m. Normal9/9 turns-33.9/+35.9deg. These pass.
Full5/5 forward37.5651m/0.5100m/2.5351deg, reverse27.5149m/1.0645m/
3.3269deg; brake37.5676m/0.4946m/2.5351deg and27.6714m/1.0964m/3.3951deg.
Reject the complete candidate. Log acf820481a5a497b3b5bfc8e20ff874d6f760bf7ee75b74b0fbbb1dbb6661df2,
no assertion. No capture flag in this comparison. The larger model also
travels roughly twice as fast; this is not a unique size/solver proof.

Distinct scale2_half_speed changes only first/high angularVelocity2->1 and
reverse0.75->0.375 on the coherent scale2 pristine sources. Full State suite
with unchanged gates is running. Native cameras now accept an explicit scale
factor; factor2 will frame this larger body. Helpers syntax checked, native
scaled framing still pending. No production source/package/install changes.
254 completed WALL-E schedules/63 State before the new speed trial, plus3
stock controls and1 separate SSL marker park.
