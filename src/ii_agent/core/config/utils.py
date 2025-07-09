import argparse
from ii_agent.core.config.ii_agent_config import IIAgentConfig


def load_ii_agent_config() -> IIAgentConfig:
    """Load the IIAgent config from the environment variables."""
    return IIAgentConfig()

def setup_config_from_args(args: argparse.Namespace) -> IIAgentConfig:
    """Load the IIAgent Pydantic Settings and override with CLI arguments."""

    config = load_ii_agent_config()

    if args.max_turns:
        config.max_turns = args.max_turns
    
    if args.max_tokens:
        config.max_output_tokens_per_turn = args.max_tokens
    
    if args.no_multiline:
        config.cli.multiline_input = False
    
    if args.no_confirmation:
        config.cli.confirmation_mode = False
    
    return config

def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = get_parser()
    args = parser.parse_args()

    if args.version:
        print(f'II-Agent version: {__version__}')
        sys.exit(0)

    return args

def get_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog='ii-agent',
        description='II-Agent CLI - Intelligent Agent Platform',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  ii-agent                              # Interactive mode
  ii-agent --task "Build a website"     # Direct task execution
  ii-agent --file task.txt              # Task from file
  ii-agent --name "My Session"          # Named session
  ii-agent --workspace ./project        # Set workspace directory
  ii-agent --model gpt-4o               # Use specific model
  ii-agent --settings                   # Open settings configuration
        '''
    )
    
    # Task input options
    task_group = parser.add_mutually_exclusive_group()
    task_group.add_argument(
        '--task', '-t',
        type=str,
        help='Task to execute directly'
    )
    task_group.add_argument(
        '--file', '-f',
        type=str,
        help='File containing task to execute'
    )
    
    # Session options
    session_group = parser.add_argument_group('Session Options')
    session_group.add_argument(
        '--name', '-n',
        type=str,
        help='Name for the session'
    )
    session_group.add_argument(
        '--resume', '-r',
        type=str,
        help='Resume session by ID or name'
    )
    session_group.add_argument(
        '--list-sessions',
        action='store_true',
        help='List all available sessions'
    )
    
    # Configuration options
    config_group = parser.add_argument_group('Configuration Options')
    config_group.add_argument(
        '--config', '-c',
        type=str,
        help='Path to configuration file'
    )
    config_group.add_argument(
        '--workspace', '-w',
        type=str,
        help='Workspace directory path'
    )
    config_group.add_argument(
        '--settings',
        action='store_true',
        help='Open settings configuration'
    )
    
    # LLM options
    llm_group = parser.add_argument_group('LLM Options')
    llm_group.add_argument(
        '--model', '-m',
        type=str,
        help='LLM model to use (e.g., gpt-4o, claude-3-5-sonnet-20241022)'
    )
    llm_group.add_argument(
        '--api-key',
        type=str,
        help='API key for LLM service'
    )
    llm_group.add_argument(
        '--base-url',
        type=str,
        help='Base URL for LLM API'
    )
    llm_group.add_argument(
        '--temperature',
        type=float,
        help='Temperature for LLM responses (0.0-1.0)'
    )
    
    # Agent options
    agent_group = parser.add_argument_group('Agent Options')
    agent_group.add_argument(
        '--agent',
        type=str,
        default='FunctionCallAgent',
        help='Agent type to use (default: FunctionCallAgent)'
    )
    agent_group.add_argument(
        '--max-turns',
        type=int,
        default=200,
        help='Maximum number of turns (default: 200)'
    )
    agent_group.add_argument(
        '--max-tokens',
        type=int,
        help='Maximum tokens per turn'
    )
    
    # CLI behavior options
    cli_group = parser.add_argument_group('CLI Options')
    cli_group.add_argument(
        '--no-multiline',
        action='store_true',
        help='Disable multiline input mode'
    )
    cli_group.add_argument(
        '--no-confirmation',
        action='store_true',
        help='Disable confirmation mode for dangerous operations'
    )
    cli_group.add_argument(
        '--no-banner',
        action='store_true',
        help='Skip displaying the banner'
    )
    cli_group.add_argument(
        '--output-format',
        choices=['text', 'json', 'yaml'],
        default='text',
        help='Output format (default: text)'
    )
    
    # Development options
    dev_group = parser.add_argument_group('Development Options')
    dev_group.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode'
    )
    dev_group.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        default='WARNING',
        help='Set logging level (default: WARNING)'
    )
    dev_group.add_argument(
        '--log-file',
        type=str,
        help='Log file path'
    )
    
    # Version and help
    parser.add_argument(
        '-v',
        '--version',
        action='store_true',
        help='Show version information'
    )
    
    return parser

