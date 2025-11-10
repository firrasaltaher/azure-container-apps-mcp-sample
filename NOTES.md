## What Have I Done, and where am i stuck?

### What have I done?

- deployed container app mcp server: mcppoc-app-uxxrze3aqrsoc
- can call health endpoint via APIM, using the x-api-key: https://containerappendpoint/health
- can call other endpoints via APIM: https://containerappendpoint/sse
- run locally as MCP server
- imported container app into APIM as API (maybe bad idea?)
- tested via APIM tests that i can call tools
- tested with npx @modelcontextprotocol/inspector and got a lot further, noticed a lot more errors with implementation
- updated implementation to work with /mcp endpoint
- now this works with APIM.  don't need to import it as a API, can import as MCP server directly

