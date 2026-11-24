"""MCP server: Weather and Local Pulse.

Forecast from Open-Meteo, business advice from deterministic rules. If the
forecast service does not answer, this returns unavailable rather than a guess.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from ..tools import weather_tool

mcp = MCPServer("arithva-weather")


@mcp.tool()
def forecast(days_ahead: int = 1, place: str = "Kalaburagi") -> dict:
    """Forecast for a day, with what it means for a small business.

    Returns temperature, rain probability, advice drawn from fixed bands, and
    any local event whose season covers that date. Up to six days ahead.
    """
    return weather_tool.forecast(days_ahead=days_ahead, place=place)


if __name__ == "__main__":
    mcp.run()
