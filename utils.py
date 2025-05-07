from argparse import ArgumentParser


def parse_common_args(parser: ArgumentParser):
    parser.add_argument(
        "--workspace",
        type=str,
        default="./workspace",
        help="Path to the workspace",
    )
    parser.add_argument(
        "--logs-path",
        type=str,
        default="agent_logs.txt",
        help="Path to save logs",
    )
    parser.add_argument(
        "--needs-permission",
        "-p",
        help="Ask for permission before executing commands",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--use-container-workspace",
        type=str,
        default=None,
        help="(Optional) Path to the container workspace to run commands in.",
    )
    parser.add_argument(
        "--docker-container-id",
        type=str,
        default=None,
        help="(Optional) Docker container ID to run commands in.",
    )
    parser.add_argument(
        "--minimize-stdout-logs",
        help="Minimize the amount of logs printed to stdout.",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--project-id",
        type=str,
        default=None,
        help="Project ID to use for Anthropic",
    )
    parser.add_argument(
        "--region",
        type=str,
        default=None,
        help="Region to use for Anthropic",
    )
    parser.add_argument(
        "--context-manager",
        type=str,
        default="file-based",
        choices=["file-based", "standard"],
        help="Type of context manager to use (file-based or standard)",
    )
    return parser
