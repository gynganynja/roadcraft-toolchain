# D11 visual and campaign reviewer claim handoff

The regression gate verifies detached Ed25519 approvals. It does not make a
visual or campaign decision. The current AAA candidate has failed technical
capture evidence, so there is nothing ready to approve. This handoff applies
only after a new, complete baseline/candidate capture and the required
campaign checks exist.

Install the verifier with `python -m pip install -e ".[review]"`. The `review`
extra declares `cryptography>=42`; the Windows CI job installs that extra and
runs the signed-claim test. The verifier uses the
[documented Ed25519 public-key API](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/).

## Before asking a reviewer to sign

1. Run `python -m roadcraft.regression PATH_TO_POLICY --json` against the exact
   policy and keep the JSON result. Check `technicalPassed`, all 45 required
   image pairs, capture and package links, and every required metric. The CLI
   exit code reflects the technical gate; **inspect `releaseReady` separately**.
2. Give the visual reviewer the exact images and comparison report. Give the
   campaign reviewer the actual shop-spawn, handling, visible track/trail and
   physical-rut evidence. Each reviewer writes a separate, nonempty UTF-8
   review note or play receipt recording their decision, observations and any
   unresolved issue. Private-editor captures cannot replace campaign play.
3. Record the candidate package SHA-256 and `gateDigest` from that same gate
   result. A change to the policy's gated artifacts or thresholds requires a
   new result and fresh approvals.

## Reviewer-controlled signing

Each real reviewer keeps their Ed25519 private key under their own control and
provides the corresponding 32-byte raw public key through an authenticated
handoff. The maintainer verifies the reviewer identity and stores only the
base64-encoded public key in an external JSON trust store, for example
`{"Reviewer Name": "BASE64_RAW_PUBLIC_KEY"}`. Keep private keys, the trust
store, and unsigned work in separate locations; do not commit a private key.
No key or approval is created by this plan.

For each stage, the reviewer approves the actual evidence, hashes their final
review note or play receipt, and signs a claim with exactly these fields:

```json
{
  "stage": "visual",
  "decision": "approved",
  "reviewer": "Reviewer Name",
  "signedAtUtc": "2026-09-28T00:00:00+00:00",
  "candidatePackageSha256": "64-lowercase-hex-candidate-package-hash",
  "gateDigest": "64-lowercase-hex-gate-digest",
  "evidence": {
    "path": "reviews/visual-review.md",
    "sha256": "64-lowercase-hex-review-file-hash"
  }
}
```

Use `stage: "campaign"` with its **own** campaign play receipt for the separate
decision. The two stage files must have distinct paths and contents; the gate
leaves campaign pending if either the resolved path or SHA-256 is reused. The
displayed date, path and hashes are placeholders, not a valid
approval. `evidence.path` is a local path resolved relative to the regression
policy file (or an absolute path); it is not relative to the detached approval
receipt. The review file must exist, be nonempty UTF-8, be at most 16 MiB, and
match `evidence.sha256` byte for byte. Sign the UTF-8 bytes of Python's
`json.dumps(claim, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`.
The detached receipt has `schemaVersion: 1`, that `claim`, and a base64
Ed25519 `signature`. Pin the SHA-256 of each complete receipt in the policy's
`approvals.visual` or `approvals.campaign` `{path, sha256}` entry. The paths
resolve relative to the policy file unless absolute. Pass the external trust
store with `--trust-store PATH` when rerunning the gate.

The gate rejects an untrusted key, invalid signature, wrong stage, candidate
hash or gate digest. It also leaves the stage pending if the signed claim lacks
the evidence pin or that file is missing, empty, not UTF-8, too large, or has
changed. Both signed decisions, both intact stage-specific review files, and a
passing technical gate are needed for `releaseReady: true`. If a reviewer
declines, records a concern, or evidence changes, keep acceptance pending and
address that finding. The gate verifies authenticity and file integrity; a
person still has to judge the substance of the review and campaign play.

Existing approval receipts with claims that omit `evidence` remain readable
but are now **pending**, even when their signatures are valid. To migrate, keep
the original note or play receipt, confirm it describes the same candidate and
gate, add its actual `{path, sha256}` to the claim, obtain a fresh signature
from the real reviewer, and update that stage's approval receipt SHA-256 pin in
the policy. A maintainer cannot append an evidence pointer to an old claim or
reuse its old signature. Pending policies with no approvals need no migration.
