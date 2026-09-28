"""Synthetic MCP dispatch checks; these tests never connect to Painter."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from mcp.server.fastmcp.exceptions import ToolError


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from substance_painter_mcp import server  # noqa: E402
from substance_painter_mcp.operations import PainterOperations  # noqa: E402


class FakeOperations:
    """Fail safe if dispatch reaches an operation during a denied call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self.remote = self

    def __getattr__(self, name: str):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return {"syntheticOperation": name}

        return record


def minimal_arguments(input_schema: dict) -> dict:
    """Satisfy each required MCP field without constructing Painter inputs."""
    def dummy_value(field: dict):
        if "enum" in field:
            return field["enum"][0]
        if "anyOf" in field:
            return dummy_value(next(choice for choice in field["anyOf"]
                                    if choice.get("type") != "null"))
        field_type = field.get("type")
        if field_type == "string":
            return "synthetic"
        if field_type == "integer":
            return 7
        if field_type == "number":
            return 1.0
        if field_type == "boolean":
            return False
        if field_type == "array":
            return []
        if field_type == "object":
            return {}
        raise AssertionError(f"Update the synthetic argument generator for {field!r}")

    properties = input_schema.get("properties", {})
    return {name: dummy_value(properties[name])
            for name in input_schema.get("required", [])}


class WriteGateTests(unittest.TestCase):
    def test_every_registered_noninspection_tool_is_gated(self) -> None:
        async def exercise() -> None:
            tools = await server.mcp.list_tools()
            self.assertEqual(len(tools), 79)
            self.assertEqual({tool.name for tool in tools if tool.annotations.readOnlyHint},
                             server.READ_ONLY_TOOLS)
            self.assertEqual(sum(not tool.annotations.readOnlyHint for tool in tools), 45)

            fake = FakeOperations()
            with patch.object(server, "operations", fake), patch.dict(
                os.environ, {}, clear=True
            ):
                for tool in tools:
                    if tool.name in server.READ_ONLY_TOOLS:
                        self.assertFalse(tool.annotations.destructiveHint, tool.name)
                        continue
                    self.assertTrue(tool.annotations.destructiveHint, tool.name)
                    with self.subTest(tool=tool.name):
                        with self.assertRaisesRegex(ToolError,
                                                    server.PROJECT_WRITE_ENV):
                            await server.mcp.call_tool(
                                tool.name, minimal_arguments(tool.inputSchema)
                            )
            self.assertEqual(fake.calls, [])

        asyncio.run(exercise())

    def test_dispatch_allows_inspection_and_denies_representative_writes(self) -> None:
        async def exercise() -> None:
            fake = FakeOperations()
            examples = (
                ("delete_layer", {"uid": 7}),
                ("create_fill_layer", {"name": "scratch"}),
                ("start_bake", {"texture_set": "scratch"}),
                ("cancel_bake", {"job_id": "scratch"}),
                ("open_project", {"project_path": "C:/scratch.spp"}),
                ("save_project_copy", {"output_path": "C:/scratch.spp"}),
                ("export_textures", {"output_directory": "C:/scratch",
                                     "preset": "scratch"}),
                ("select_layers", {"uids": [7]}),
                ("execute_python", {"code": "result = 1"}),
            )
            with patch.object(server, "operations", fake), patch.dict(
                os.environ, {server.PROJECT_WRITE_ENV: "0"}
            ):
                _, status = await server.mcp.call_tool("painter_status", {})
                self.assertEqual(status, {"syntheticOperation": "status"})
                for name, args in examples:
                    with self.subTest(tool=name):
                        with self.assertRaisesRegex(ToolError,
                                                    server.PROJECT_WRITE_ENV):
                            await server.mcp.call_tool(name, args)
            self.assertEqual(fake.calls, [("status", (), {})])

        asyncio.run(exercise())

    def test_explicit_opt_in_preserves_separate_raw_python_and_path_gates(self) -> None:
        async def exercise() -> None:
            fake = FakeOperations()
            with patch.object(server, "operations", fake), patch.dict(
                os.environ,
                {server.PROJECT_WRITE_ENV: "1", "SP_MCP_ALLOW_EXECUTE_PYTHON": "0",
                 "SP_MCP_EXPORT_ROOTS": ""},
            ):
                _, deleted = await server.mcp.call_tool("delete_layer", {"uid": 7})
                self.assertEqual(deleted, {"syntheticOperation": "delete_layer"})
                with self.assertRaisesRegex(ToolError, "Raw Python execution is disabled"):
                    await server.mcp.call_tool("execute_python", {"code": "result = 1"})
                with self.assertRaisesRegex(PermissionError, "SP_MCP_EXPORT_ROOTS"):
                    PainterOperations._validate_allowed_path(
                        "C:/scratch", "SP_MCP_EXPORT_ROOTS", "Texture export"
                    )
            self.assertEqual(fake.calls, [("delete_layer", (7,), {})])

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
