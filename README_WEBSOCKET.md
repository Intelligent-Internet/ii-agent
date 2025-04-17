# Agent WebSocket Interface

This project extends the Agent CLI to support real-time communication with a frontend application using WebSockets.

## Features

- Real-time communication between the Agent and frontend clients
- Built with FastAPI and WebSockets
- Simple HTML/CSS/JS frontend included
- Support for querying the Agent and receiving responses
- Cancel functionality for long-running queries
- Automatic reconnection on disconnection

## Requirements

The WebSocket server requires the following Python packages:

```
fastapi
uvicorn
websockets
```

These should be installed in addition to the existing project dependencies.

## Quick Start

1. Run the WebSocket server:

```bash
python ws_server.py --workspace ./workspace
```

2. Open a web browser and navigate to:

```
http://localhost:8000
```

The server automatically serves the frontend interface from the `frontend` directory.

## Command Line Options

The WebSocket server supports the same command line options as the CLI, with additional WebSocket-specific options:

```
--workspace PATH          Path to the workspace (default: ./workspace)
--logs-path PATH          Path to save logs (default: agent_logs.txt)
--needs-permission, -p    Ask for permission before executing commands
--use-container-workspace PATH  Path to the container workspace to run commands in
--docker-container-id ID  Docker container ID to run commands in
--minimize-stdout-logs    Minimize the amount of logs printed to stdout
--host HOST               Host to run the server on (default: 0.0.0.0)
--port PORT               Port to run the server on (default: 8000)
```

## WebSocket API

The WebSocket server provides a simple JSON-based API for communication:

### Endpoint

- `/ws` - The WebSocket endpoint

### Client Messages

Messages sent from the client to the server follow this format:

```json
{
  "type": "message_type",
  "content": {
    // message-specific data
  }
}
```

#### Supported Message Types

1. `query` - Send a query to the Agent
   ```json
   {
     "type": "query",
     "content": {
       "text": "Your query text",
       "resume": false
     }
   }
   ```

2. `workspace_info` - Request information about the workspace
   ```json
   {
     "type": "workspace_info",
     "content": {}
   }
   ```

3. `ping` - Keep the connection alive
   ```json
   {
     "type": "ping",
     "content": {}
   }
   ```

4. `cancel` - Cancel the current Agent task
   ```json
   {
     "type": "cancel",
     "content": {}
   }
   ```

### Server Messages

The server responds with messages in the following format:

```json
{
  "type": "message_type",
  "content": {
    // message-specific data
  }
}
```

#### Server Message Types

1. `connection_established` - Sent when a client connects
2. `workspace_info` - Contains information about the workspace
3. `processing` - Indicates that a query is being processed
4. `agent_response` - Contains the Agent's response to a query
5. `error` - Sent when an error occurs
6. `system` - System notifications (e.g., cancellations)
7. `pong` - Response to a ping message

## Customizing the Frontend

The frontend is a simple HTML/CSS/JavaScript application located in the `frontend` directory. You can customize it to fit your needs by modifying the HTML, CSS, and JavaScript code.

## Integration with Other Frontends

To integrate with other frontends, simply connect to the WebSocket endpoint and follow the message format described above.

Example (JavaScript):

```javascript
const socket = new WebSocket('ws://localhost:8000/ws');

socket.addEventListener('open', () => {
  console.log('Connected to WebSocket server');
  
  // Send a query
  socket.send(JSON.stringify({
    type: 'query',
    content: {
      text: 'List files in the workspace',
      resume: false
    }
  }));
});

socket.addEventListener('message', (event) => {
  const message = JSON.parse(event.data);
  console.log('Received:', message);
  
  // Handle different message types
  switch (message.type) {
    case 'agent_response':
      console.log('Agent response:', message.content.text);
      break;
    // Handle other message types
  }
});
```

## Security Considerations

This implementation is for development purposes and lacks security features required for production environments:

- No authentication or authorization mechanisms
- No rate limiting
- No encryption (unless deployed behind HTTPS)

For production deployments, consider adding proper security measures.

## Troubleshooting

If you encounter any issues:

1. Check that all required packages are installed
2. Verify that the WebSocket server is running and accessible
3. Check the server logs for error messages
4. Ensure the port is not blocked by a firewall

## License

This project is licensed under the same terms as the parent project. 