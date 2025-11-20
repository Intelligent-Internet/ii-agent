"""Main CLI entry point for ii-agent."""
import argparse
import asyncio
import logging
import os
import uvicorn

logger = logging.getLogger(__name__)


def main():
    """Main entry point for the WebSocket server."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="WebSocket Server for interacting with the Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ii-agent                         # WebSocket server mode (default)
  ii-agent --port 8080             # Server on custom port
  ii-agent --repl                  # Interactive REPL mode
  ii-agent --repl --workspace .    # REPL with workspace
"""
    )

    # Mode selection
    parser.add_argument(
        "--repl",
        action="store_true",
        help="Run in interactive REPL mode (aider-style CLI)",
    )

    # REPL options
    parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help="Workspace directory for REPL mode (default: current directory)",
    )

    # Server options (used when --repl is not specified)
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to run the server on",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run the server on",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes"
    )
    parser.add_argument(
        "--reload",
        default=False,
        type=bool,
        help="Enable auto-reload for development (not recommended for production)",
    )

    args = parser.parse_args()

    # Run in REPL mode
    if args.repl:
        from ii_agent.cli.repl import main_repl
        workspace = args.workspace or os.getcwd()
        logger.info(f"Starting REPL mode in workspace: {workspace}")
        asyncio.run(main_repl(workspace))

    # Run in server mode (default)
    else:
        logger.info(f"Starting WebSocket server on {args.host}:{args.port}")
        uvicorn.run(
            "ii_agent.server.app:app",
            host=args.host,
            port=args.port,
            workers=args.workers,
            reload=args.reload
        )


if __name__ == "__main__":
    main()
