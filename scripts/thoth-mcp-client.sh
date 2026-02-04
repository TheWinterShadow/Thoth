#!/bin/bash
export PATH=/home/linuxbrew/.linuxbrew/bin:/usr/local/bin:/usr/bin:/bin
exec npx mcp-remote https://thoth-mcp-server-kp5w37kooa-uc.a.run.app/mcp/sse --header "Authorization: Bearer $(gcloud auth print-identity-token)"
