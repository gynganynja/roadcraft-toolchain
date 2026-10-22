# Engine audio acquisition and audition

Scope: recording-derived engine assets before Wwise authoring, packaging or
installation. The 2026-10-09 CAT 793D audition is a free approximation, not a
verified recording of that truck. Numerical, audible, runtime and campaign
acceptance remain distinct.

## Source identity, rights and quality are separate checks

**Build / Open, 793D audition 2026-10-09:** save the creator, original page,
download page, explicit licence evidence, downloaded-byte SHA-256 and decoded
sample format. Preserve downloaded originals separately from processing outputs.
An engine model in search tags does not identify the recorded engine. An actual
FLAC/WAV container does not establish microphone quality, lossless upstream
capture, isolated exhaust, or independently recorded RPM/load coverage.

Two public CC0 sources were acquired: [qubodup's mirrored truck idle loops](https://creazilla.com/media/audio/15407230/truck-engine-idle-loops)
([Freesound origin](https://freesound.org/people/qubodup/sounds/187564/)) and
[Joseph SARDIN's Roadworks #1](https://bigsoundbank.com/roadworks-1-s0631.html)
([licence](https://bigsoundbank.com/licenses.html)). Both decode to 48 kHz,
16-bit PCM. qubodup describes extraction from a government video. Roadworks
includes surrounding work and unidentified truck/backhoe engines. Neither
establishes 793D or 3516B HD identity. Saved acquisition evidence is
`cat793d_audio_20261009/source_manifest.json` and `evidence/` in the project
workspace. The creators' stated licence is recorded; source identity is **Open**.

The inspected free sources did not establish a complete exact-truck recording
set. That bounded search finding does not prove none exists. The user explicitly
authorized an approximation, free existing downloads and no owner outreach.
Do not silently broaden those limits. The professional
[HISSandaROAR quarry pack](https://hissandaroar.com/v3/soundlibrary/fx001-quarry-dump-truck/)
is a paid Komatsu HD465 source; it did not qualify. Exact-engine video leads
without verified reuse rights were references only. No media was taken from
them. Freesound 429/403 responses were a failed access path, not permission to
bypass restrictions. A missing in-app browser runtime and unavailable optional
game-dev CLI did not prevent ordinary public HTTP acquisition/local validation.

## Derived controls do not create recorded coverage

**Build / Inferred, this audition only:** stable source regions can be filtered,
overlapped, pitched and levelled into labelled approximation loops. The audition
used Roadworks 35–47 seconds for the low-frequency bed and qubodup 24–31 seconds
for mechanical texture. It produced six nominal RPMs (700–1960), each with two
load labels, from those same recordings. These are control labels, not measured
source RPMs or independently recorded loaded/unloaded conditions. The range
follows the user's proposed simulator configuration, not a validated truck
engine calibration.

An evenly firing four-stroke V16 has eight firing events per revolution, but
aligning a selected spectral feature to that rate does not verify that feature
as the recording's firing fundamental or reproduce the truck's firing-order
acoustics. The selected 63.721 Hz feature remains unverified. No authentic
startup, shutdown, fan or turbo takes were supplied. A filtered cab comparison
is an artistic version, not a measured cab response. Exporting processed masters
at 24 bits does not improve 16-bit source precision.

Evidence: `cat793d_audio_20261009/tools/build_audition.py`, `asset-spec.json`,
`reports/audition_quality.json` and `reports/source_decisions.md`. Label asset
identity and missing coverage in the audition and any later release notes.

## Validate delivered bytes and keep acceptance stages separate

**Build, this audition:** decoded output checks covered format, hashes,
non-finite/clipped samples, 4× oversampled peak estimates and the loop's end-to-start
sample step against ordinary adjacent steps. Twelve 7.88-second mono loops and
two 50-second previews use 48 kHz/24-bit WAV; MP3s are listening copies. Worst WAV
estimated true peak was −3.20 dBTP. `tools/verify_delivery.py` independently
checks hashes, source-page evidence, metadata, decoded WAV seams and decoded
MP3 copies; its receipt is `reports/delivery_verification.json`.

These checks identify corruption, clipping and a large numerical boundary jump;
they do not prove perceptual loop continuity or engine realism. Listener
acceptance is **Open**. Separate audition approval from Wwise compilation,
package identity, installation receipts, runtime playback and campaign
acceptance. This audition built no sound bank or mod and wrote no installed
package. Its current-package snapshot differed from the historical RC26
installed registry; no accepted pin or registry was changed to fit it. Select
and verify the current project baseline before later authoring/install work.

The current signal-processing choices are one candidate, not a universal
engine-creation model. A shared DSP/QA framework is deferred: repeated accepted
engine assets with stable requirements would justify one. Project scripts and
durable manifests retain the reproducible technique without enforcing an
unverified acoustic hypothesis across mods.

## Runtime bank compatibility remains a separate gate

**Build / reported native evidence, historical 793D RC13:**
`cat793d_thiess_fix/ENGINE_SOUND_FIX_20260911.md` records a missing
`CrankcaseAudioREVModelPlayer` dependency in the Baikal bank, despite updating
RPM controls and existing resources. RC13 substituted stock Greenway 740 Cross
sample-based events and standard Vorbis sources. Audible in-game acceptance
remained pending in that report. This history does not establish compatibility
of a new custom bank. Inspect its codecs/plugins, event dependencies and runtime
logs, then listen in the intended editor/game. A valid WAV audition cannot
establish a usable RoadCraft bank.

## Getting engine audio into a mod: routes and limits (static RE, 2026-10-14)

Grades: C = code, binaries or SSL; R = retail data; I = inferred. Full evidence
is in `C:\RC_RE\research\sound_semantics.md`. No game or editor run was made, so
none of this has been heard.

**Binding (R/C).** A class plays sounds by event name, from its blueprints
(`PlaySoundOnEmitter.soundDesc.type.name`). Its `.cls.resource` `linksSound`
must list every event the class plays. Events pull in their banks through
resource links. An event missing from `linksSound` has no bank loaded, so it is
silent. RPM, gear, speed and acceleration reach Wwise through
`SetSoundEmitterParameter` nodes on `rtpc_vehicle_rpm` / `_gear` / `_speed` /
`_acceleration`. The rpm is signed (negative in reverse) and is read every
0.1 s. It comes from `gearRatio` × `finalDriveRatio` × wheel ω, which has no
physics effect. The `Body` graph sets these switches:
- `switch_vhc_type` from the class `truckType`;
- `switch_vhc_condition` (old/new);
- the horn `ssw_vhc_name` from `truckName`, which must be a retail state.

**Without Wwise (R/C).**
- Mix any retail events into the class graph, as the Goliath RC5 did. Rename the
  family prefix, fix the switches, and regenerate `linksSound`.
- Reshape the response by scaling or offsetting rpm in the graph, or by changing
  `gearRatio`.
- `mod_sounds_gen convert-external-sources` turns WAVs into PCM16 external
  sources. Only three retail events accept an external source:
  `vo_ext_talker_story_*`. Each is a 2D one-shot on a VO bus. That route can give
  a cab-only beep, but not an engine (I, untested).

**REV (R/C).**
- 26 of the 49 truck families use Crankcase REV. Each REV source has a
  212-byte parameter block, a model of about 2.6 MB, and its RTPC curves, all in
  the bank. Its idle-to-full range is |rpm| 800–1500, and the note stops rising
  above 1500.
- Mods cannot change REV without Wwise and the Crankcase authoring plugin.
- `Roadcraft ModEditor.exe` has no REV plugin registration, while the retail exe
  and `wwise_wrapper_dll` do. Expect REV engines to be silent in editor play mode
  and on the bench (I). This fits the 793D "missing CrankcaseAudioREVModelPlayer"
  report. **Judge borrowed REV engines in retail only.**
- The TK53 Krot, Warden, Kronenwerk and other families are sample-based Blend
  containers, which play everywhere.

**Your own engine needs Wwise 2019.2.15.7667 (C).** Use the SDK
`mods_source/wwise/mod_snd` project and follow these rules:
- Give the bank and its events unique names. The template defaults `mod_bank`
  and `mod_event` collide across mods, because bank and event IDs are FNV-1
  hashes of their names.
- Ship no init bank. Post-generation strips it.
- Route only to existing busses (`actors`).
- Use the existing RTPC names.
- Generate banks so that the pre- and post-generation `mod_sounds_gen` steps
  write the `sounds/` resources.

A hand-patched clone of a retail sample bank is possible in principle, but it
is unbuilt and untested. `roadcraft sound clone-bank` now builds one (next
section).

## Cloning a retail sample bank without Wwise (2026-10-23)

**Build only, unbenched.** `roadcraft sound clone-bank` writes a hand-patched
clone of a retail sample bank. Nobody has loaded or heard one in the game or the
editor yet. Grades and evidence are in `sound_semantics.md` §7.

**No MP3 importer exists (C).**
- No editor, SDK or tool reads MP3 or OGG.
- `mod_sounds_gen convert-external-sources` reads `*.wav` only. It calls
  ffmpeg, through the empty `ffmpeg-tool` slot in `wwise_common.prjenv`, only to
  change a WAV's sample rate or channel count.
- Convert an MP3 to WAV outside the toolchain first.

**What the command does.**
- It reads the donor `.bnk`, its event resources and its streamed media bundle
  from the retail paks. Only the 23 sample-based `vhc_*` banks are accepted;
  REV, FX and music banks are refused.
- It keeps the donor's whole structure: the layer crossfades and pitch on
  `rtpc_vehicle_rpm`, the `fuel` switch, attenuation, bus, loop flags and
  InitialDelay.
- It changes only the IDs:
  - bank ID = FNV-1 of `--name`;
  - event names = the donor prefix replaced by `--name`, with ID = FNV-1 of the
    new name;
  - every object, layer and media ID is re-derived from `--name`, and the result
    is checked against all 85 retail banks.
- Roles you assign get PCM16 `.wem` media, laid out byte for byte like retail
  `tech.bnk`'s one PCM media. Unassigned roles keep the donor's Vorbis bytes.
- All media goes into the bank's DATA chunk, so the clone needs no media bundle.
- It writes `<out>/sounds/banks/<name>.sound_bank.resource`,
  `sounds/desktop/<name>.bnk` and one `sounds/events/<event>.sound_event.resource`
  per donor event. These are CRLF, like retail.

Usage:

```
roadcraft sound clone-bank --donor vhc_vostok_tk53krot --name <bank>          # list roles
roadcraft sound clone-bank --donor vhc_vostok_tk53krot --name <bank> \
    --clip engine.idle=idle.wav --clip engine.mid=high.wav \
    --clip engine.high=high.wav --clip engine.overlay=high.wav \
    --clip engine_start.filled.1=start.wav --clip engine_start.filled.2=silence \
    --clip engine_start.no_fuel=start.wav --clip engine_stop=stop.wav \
    --out <project>/mods_source
```

- `--clip` takes a role, a role prefix (`acc` assigns `acc.1`…`acc.6`), or a
  Sound ID.
- `silence` gives a 50 ms silent clip.
- Accepted WAVs are 8/16/24/32-bit integer or 32-bit float PCM, mono or stereo.
  24/32-bit is rounded to 16-bit with no dither, and the sample rate is kept.
- The report gives the new event and Sound IDs, each loop's end-to-start step
  against its median step, and which roles still carry donor audio.

**TK53 Krot roles (R).** The rpm values are the positive side of the crossfade
curves.

| Role | Plays | Audible rpm | Full rpm |
|---|---|---|---|
| `engine.idle` | loop | 0–980 | 0–800 |
| `engine.mid` | loop | 801–1195 | 981–1031 |
| `engine.high` | loop | 1032–1499 | 1196–1234 |
| `engine.overlay` | loop on a second layer | 945–1500 | 1500 |

- Pitch, layer 1: +0 cents at 800, rising to +300 cents at 1500.
- Pitch, layer 2: +0 cents at 694, rising to +200 cents at 1500.
- `engine_start.filled.1`: the start, after a 0.7 s InitialDelay.
- `engine_start.filled.2`: the crank.
- `engine_start.no_fuel`: the crank alone.
- `engine_stop`: a one-shot.

**Loops (R/I).** The donor loops with the Sound's `Loop` property (infinite).
The PCM clone carries no `smpl` loop points, so the whole file loops (I). Clips
must therefore be seamless end to start. 48 kHz is fine: the Krot's own media is
48 kHz.

**Using the clone (C/I).**
1. Point the class's `PlaySoundOnEmitter` nodes at `<name>_engine`,
   `_engine_start` and `_engine_stop`.
2. Regenerate `linksSound` (`res://sounds/events/<e>.sound_event.resource`).
3. Build.

**Bench still needed (U):**
- The bank loads beside the retail Krot with no "already loaded" or ID warning.
- Every role is heard.
- The PCM header is accepted.
- The loop seams are inaudible.
- The editor plays it, as expected for a sample bank.
- `mod_pak_builder` picks up `sounds/desktop/<name>.bnk` through the bank
  resource.

**Route 2 does not work (I).** Overriding the retail Krot media from a mod is
not per-mod. Mod pak layers are global. `sounds/banks`, `sounds/desktop` and
`sounds/media_bundles` are not cached tag directories, so the retail entry is
kept. The SDK builder also drops retail tags.

Integration: this article is listed in [the library index](README.md) and is
available through `roadcraft library audio-assets`. Shared code added on
2026-10-23: `roadcraft.wwise_bank` (the v135 bank reader) and `roadcraft.sound_clone`
(`roadcraft sound clone-bank`). Both are build-only. No native recipe or
installation authority changed.
