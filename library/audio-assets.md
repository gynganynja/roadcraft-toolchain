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

Integration: this article is listed in [the library index](README.md) and is
available through `roadcraft library audio-assets`. No shared code, native recipe
or installation authority changed.
