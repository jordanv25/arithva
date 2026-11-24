"""MCP servers.

Five servers, one per domain. Each wraps the same functions in backend/tools
that the web app calls, so an MCP client and the web app get identical answers
from identical code. Nothing is reimplemented for MCP.

Run one with:

    python -m backend.mcp_servers.scheme_server

They speak stdio, so any MCP client (Claude Desktop, an IDE, your own agent)
can mount them.
"""
