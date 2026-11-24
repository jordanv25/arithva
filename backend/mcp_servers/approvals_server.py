"""MCP server: Approvals.

Note what is absent: there is no approve tool.

A calling model can work out how many signatures an amount needs, prepare an
application, and read the status of one. Approval happens only when enough
valid officer signatures reach the server over the HTTP API, verified against
officer public keys. No prompt, jailbreak or clever tool call from this surface
can approve anything, because the capability does not exist here.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from .. import db
from ..tools import approvals_tool
from ..tools.money import rupees_to_paise

db.init(seed=True)

mcp = MCPServer("arithva-approvals")


@mcp.tool()
def quorum_for(amount_inr: float, risk_flags: list[str] | None = None) -> dict:
    """How many officer signatures an amount needs, and why.

    The bands are design values in a rules file, not legal thresholds. Risk
    flags each add one more required signer.
    """
    return approvals_tool.quorum_for(rupees_to_paise(amount_inr), risk_flags)


@mcp.tool()
def prepare_application(applicant_id: str, scheme_id: str, scheme_name: str,
                        amount_inr: float, applicant_name: str | None = None,
                        purpose: str | None = None) -> dict:
    """Draft an application and place it in the officer queue.

    This is the furthest an agent can take a money request. The application is
    created with status 'prepared' and moves no further without signatures.
    """
    return approvals_tool.prepare_application(
        applicant_id=applicant_id,
        applicant_name=applicant_name,
        scheme_id=scheme_id,
        scheme_name=scheme_name,
        amount_inr=amount_inr,
        purpose=purpose,
    )


@mcp.tool()
def application_status(application_id: int) -> dict:
    """Read an application and the signatures collected on it so far."""
    return approvals_tool.application_detail(application_id)


if __name__ == "__main__":
    mcp.run()
