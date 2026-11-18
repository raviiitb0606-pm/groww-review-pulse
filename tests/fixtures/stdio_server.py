"""A stdio MCP server with the two workspace tools, for the stdio transport test. No writes."""

import json

from mcp.server.mcpserver import MCPServer

server = MCPServer("stdio-fake")


@server.tool()
def append_google_doc(documentId: str, text: str) -> str:
    url = f"https://docs.google.com/document/d/{documentId}/edit"
    return json.dumps({"success": True, "documentUrl": url})


@server.tool()
def send_gmail(to: str, subject: str, body: str) -> str:
    return json.dumps({"success": True, "messageId": f"stdio-{len(body)}"})


if __name__ == "__main__":
    server.run()
