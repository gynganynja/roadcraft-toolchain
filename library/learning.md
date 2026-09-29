# Integrating new knowledge

Every RoadCraft task should leave reusable knowledge in the maintained
toolchain before the agent reports completion. This applies to vehicle work,
SDK research, source/export work, builds, packaging, diagnostics, evidence,
storage and workflow improvements. Existing authorization covers recording
task findings; it does not authorize unrelated execution or installation.

## Reuse, record, integrate

1. Locate the maintained checkout through `ROADCRAFT_TOOLCHAIN` or the
   `local/toolchain.json` selector. Search the relevant library articles and
   shared tools before repeating research or writing another project helper.
2. When a task reveals a reusable fact, fix, constraint, failed approach,
   corrected assumption, user observation or useful technique, update the
   relevant subject article in the same task. Keep the entry concise and
   actionable. Merge with an existing entry instead of duplicating it.
3. Include the scope (vehicle/rig type, relevant tool version and conditions),
   evidence grade from [README.md](README.md), supporting source or exact
   build/receipt/test reference, and unresolved limits. Use **Inferred** or
   **Open** where appropriate. User feedback establishes the reported symptom;
   it does not by itself establish the proposed cause or validate the fix.
4. For a fault, update [symptoms.md](symptoms.md) with its diagnosis and remedy.
   For a project incident or drive, add the supporting history to
   [case-studies.md](case-studies.md). Preserve failed attempts that explain a
   useful limitation or prevent repeated work, without dumping full transcripts.
5. Where a lesson is supported and mechanically checkable, integrate a shared
   validator and a meaningful regression test, then connect the check to the
   relevant build/test path. Repeated manual work may instead warrant a shared
   helper, recipe or starter improvement. Prefer the existing implementation;
   do not create a general framework for a one-off observation. Do not enforce
   an unverified hypothesis as a universal rule. When automation is premature
   or disproportionate, record why and what evidence would make it useful.
6. Validate changed behavior with focused tests and required checks. Preserve
   pinned recipes; generate a new recipe when changed shared code invalidates
   its inputs. Record actual timing when claiming an efficiency improvement.
   Documentation-only edits need link/consistency checks, not wording tests.
7. Before completion, briefly identify the learning, the updated shared files,
   any automation added and any remaining uncertainty. A chat explanation or
   private memory entry alone is not integration. If there is no new reusable
   finding, do not manufacture an entry or churn the library.

## Corrections and collaboration

When new evidence contradicts an existing rule, revise the rule and grade,
explain what superseded it and retain the earlier evidence. Distinguish the
old failing build from the fix and from the build actually tested. Captured,
numerical, visual and campaign acceptance remain separate.

Keep source references traceable: use project/build IDs, repository-relative
paths and existing receipt pins where available. Label a newly computed hash
as a current snapshot, not a previous seal. Keep machine paths and installation
state in local configuration or project receipts; keep credentials out of the
library. Add a new subject article to the library index when needed.

Read current contents before editing shared files and preserve other agents'
work. If the maintained checkout cannot be updated, save the finding, evidence,
intended destination and reason in an accessible project handoff, then report
that shared integration remains incomplete. Do not silently update an obsolete
checkout or claim integration succeeded.

## Compact entry format

- **Finding and action:** What changes the next project's decisions or steps.
- **Scope and grade:** Where it applies and how firmly it is established.
- **Evidence:** Source, build/receipt, test or dated user observation.
- **Integration:** Shared rule/check/helper/recipe updated, and validation result.
- **Limits:** Open questions, exceptions, superseded claim or deferred automation.
