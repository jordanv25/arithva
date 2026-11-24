"""MCP server: Jobs.

Posting, finding, applying and accepting. Contacts stay masked until both
sides accept; offers below the minimum wage for the trade are flagged.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from .. import db
from ..tools import jobs_tool

db.init(seed=True)

mcp = MCPServer("arithva-jobs")


@mcp.tool()
def post_job(employer_id: str, trade: str, workers_needed: int, days: int,
             wage_per_day_inr: float, area: str, starts_on: str | None = None) -> dict:
    """Post a job. The result flags any wage below the recorded minimum for that trade."""
    return jobs_tool.post_job(employer_id, trade, workers_needed, days,
                              wage_per_day_inr, area, starts_on)


@mcp.tool()
def find_jobs(trade: str | None = None, area: str | None = None, limit: int = 5) -> dict:
    """Find open jobs, each with a plain-language reason for the match."""
    return jobs_tool.find_jobs(trade, area, limit)


@mcp.tool()
def apply_to_job(job_id: int, worker_id: str, worker_name: str, trade: str = "") -> dict:
    """Apply for a job. The worker's phone number stays hidden until the employer accepts."""
    return jobs_tool.apply_to_job(job_id, worker_id, worker_name, trade)


@mcp.tool()
def accept_application(application_id: int, employer_id: str) -> dict:
    """Accept an application. Only then are contact details shared between the two sides."""
    return jobs_tool.accept_application(application_id, employer_id)


if __name__ == "__main__":
    mcp.run()
