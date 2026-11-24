"""MCP server: Loan and EMI.

All arithmetic in integer paise. A calling model passes the inputs and reads
the result; it never does this maths itself.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from ..tools import loan_tool

mcp = MCPServer("arithva-loan")


@mcp.tool()
def calculate_emi(amount_inr: float, tenure_months: int = 36,
                  annual_rate_pct: float | None = None,
                  moratorium_months: int = 0) -> dict:
    """Work out the monthly instalment, total interest and total repayment.

    Uses reducing-balance interest computed in integer paise. Interest during a
    moratorium accrues and is added to the principal before the instalment is
    worked out; the result states this. Amounts come back both as digits and as
    the words people use aloud ("one lakh fifty thousand rupees").
    """
    return loan_tool.calculate_emi(amount_inr, tenure_months, annual_rate_pct, moratorium_months)


@mcp.tool()
def subsidy_estimate(scheme_id: str, project_cost_inr: float,
                     area: str = "rural", category: str = "general") -> dict:
    """Estimate the capital subsidy for a scheme that offers one.

    area is 'rural' or 'urban'; category is 'general' or 'special'.
    """
    return loan_tool.subsidy_estimate(scheme_id, project_cost_inr, area, category)


if __name__ == "__main__":
    mcp.run()
