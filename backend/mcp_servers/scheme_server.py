"""MCP server: Scheme Navigator.

Eligibility and document checklists, read from the curated rules file.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from ..tools import scheme_tool

mcp = MCPServer("arithva-schemes")


@mcp.tool()
def find_schemes(age: int = 30, trade: str = "", business_status: str = "new",
                 amount_needed_inr: float | None = None) -> dict:
    """Find government schemes an applicant may be eligible for.

    Returns eligible and ineligible schemes, each with the reasons behind the
    decision, the document checklist and the source of the rule. Eligibility is
    indicative; the implementing agency decides.
    """
    return scheme_tool.find_schemes({
        "age": age,
        "trade": trade or None,
        "business_status": business_status,
        "amount_needed_inr": amount_needed_inr,
    })


@mcp.tool()
def scheme_documents(scheme_id: str) -> dict:
    """List the documents one scheme requires, and where to apply."""
    return scheme_tool.scheme_documents(scheme_id)


@mcp.tool()
def nearest_centre(district: str = "kalaburagi") -> dict:
    """Find the nearest Common Service Centre or bank branch for a district."""
    return scheme_tool.nearest_centre(district)


if __name__ == "__main__":
    mcp.run()
