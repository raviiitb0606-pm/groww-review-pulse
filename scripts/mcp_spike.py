"""Phase 0 MCP spike: list a server's tools, optionally call one.

Usage:
  uv run python scripts/mcp_spike.py "<server launch command>"     # stdio
  uv run python scripts/mcp_spike.py https://host/mcp              # HTTP, MCP_AUTH_TOKEN from .env
  uv run python scripts/mcp_spike.py "<cmd or url>" --call TOOL_NAME '{"arg": "value"}'
Record the real tool names and argument shapes in docs/phase0-decisions.md.
"""

import asyncio
import json
import shlex
import sys

from dotenv import load_dotenv
from mcp import Client, StdioServerParameters

from pulse.config import Mcp
from pulse.mcp_gateway import connect


async def main(command: str, call: tuple[str, dict] | None) -> None:
    if command.startswith("http"):
        async with connect(Mcp(url=command)) as gateway:
            await run(gateway.client, call)
    else:
        parts = shlex.split(command)
        async with Client(StdioServerParameters(command=parts[0], args=parts[1:])) as client:
            await run(client, call)


async def run(client: Client, call: tuple[str, dict] | None) -> None:
    for tool in (await client.list_tools()).tools:
        print(f"- {tool.name}: {(tool.description or '').splitlines()[0:1]}")
        print(f"  schema: {json.dumps(tool.input_schema)}")
    if call:
        result = await client.call_tool(call[0], call[1])
        print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    load_dotenv()
    cmd = sys.argv[1]
    call = (
        (sys.argv[3], json.loads(sys.argv[4]))
        if len(sys.argv) > 4 and sys.argv[2] == "--call"
        else None
    )
    asyncio.run(main(cmd, call))
