# Desktop MCP visibility is scoped to the task project

Read-only audit on 28 September 2026 (Australia/Brisbane). No MCP configuration,
trust setting, Painter project, or installed package was changed by this audit.

| Context | Current evidence |
|---|---|
| This Codex task | Workspace and saved project `Roadcraft Modding` root: `C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package` (project ID `12229c2f-717c-4ea7-b6ee-0ca7fea0a461`). That root has no `.codex/config.toml`. The callable task tool inventory has no `roadcraft`, `substance_painter`, or `roadcraft_blender_scratch` MCP tools. |
| CLI in the Steam root | `codex mcp list` shows built-in entries, but none of the three RoadCraft project-local servers. |
| CLI in the approved dedicated checkout | `C:\RC\RoadCraftDev\toolchain\.codex\config.toml` exists. `codex mcp list` shows `roadcraft`, `substance_painter`, and `roadcraft_blender_scratch` enabled, each launched from the dedicated `.venv` with that checkout as `cwd`. Earlier real stdio probes inventoried 11, 79, and 2 tools, respectively. |

[Official OpenAI MCP documentation](https://developers.openai.com/codex/mcp)
states that `.codex/config.toml` can scope servers to a trusted project and that
the desktop app and CLI share configuration. The
[configuration precedence documentation](https://developers.openai.com/codex/config-basic)
states that project config is loaded from the project root down to the current
working directory only for trusted projects. The observed path difference is
therefore a sufficient explanation for the missing task tools; it is not
evidence that the local servers or desktop MCP transport are broken.

The dedicated checkout trust and MCP configuration were explicitly approved
earlier. This audit does not extend that approval to the Steam root. To verify
desktop MCP end to end, open a Codex task whose saved project root is the
dedicated checkout, inspect its connected MCP list, and call RoadCraft's
read-only status tool. Keep Painter closed until the user chooses to resume
its disposable-project check. A new task would be a separate user-owned task;
this audit did not create one. Current work can continue through the verified
dedicated CLI and direct read-only subprocess checks, with exact paths and
receipts, while desktop tool visibility remains unverified.
