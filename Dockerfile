FROM python:3.11-slim

# Install server dependencies
RUN pip install --no-cache-dir "mcp[cli]>=1.7.1" "secedgar==0.6.0a0"

# Copy source
WORKDIR /app
COPY . .

# Ensure local package is discoverable
ENV PYTHONPATH=/app

# The server requires SEC_EDGAR_USER_AGENT to be set at runtime
CMD ["mcp", "install", "sec_edgar_mcp/server.py", "--name", "SEC EDGAR MCP Server"]
