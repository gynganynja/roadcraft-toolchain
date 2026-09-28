"""Exercise real stdio handshakes without changing any RoadCraft artifact."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]


async def probe(name: str, module: str, arguments: list[str], tool: str) -> dict:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", module, *arguments],
        cwd=str(ROOT),
    )
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            listing = await session.list_tools()
            names = [item.name for item in listing.tools]
            if tool not in names:
                raise ValueError(f"{name}: required tool {tool!r} absent from {names}")
            result = await session.call_tool(tool, {})
            return {"server": name, "toolCount": len(names), "requiredTool": tool,
                    "isError": result.isError,
                    "response": [item.text[:400] for item in result.content
                                 if getattr(item, "type", None) == "text"]}


async def main() -> None:
    roadcraft = await probe("roadcraft", "roadcraft.mcp_server",
                            ["--registry", str(ROOT / "project.json"),
                             "--config", str(ROOT / "local" / "machine.json")],
                            "project_doctor")
    painter = await probe("substance-painter", "substance_painter_mcp.server", [],
                          "painter_status")
    print(json.dumps({"roadcraft": roadcraft, "painter": painter}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
