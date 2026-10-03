FROM python:3.13-slim

WORKDIR /app
COPY requirements-mcp.txt requirements-mcp-server.txt ./
RUN pip install --no-cache-dir -r requirements-mcp-server.txt
COPY src ./src
COPY trips ./trips

ENV PYTHONPATH=/app \
    MCP_TRANSPORT=streamable-http \
    TRAVEL_PLANNER_TRIPS_DIR=/data/trips \
    TRAVEL_PLANNER_SITE_DIR=/data/site

EXPOSE 8000
CMD ["python", "-m", "src.mcp_server.server"]
