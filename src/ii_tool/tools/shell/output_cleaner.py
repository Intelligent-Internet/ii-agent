"""Shell output cleaning and summarization using LLM."""

import logging
from typing import Optional
from ii_agent.llm.base import LLMClient, TextPrompt, TextResult, LLMMessages
import re

logger = logging.getLogger(__name__)

class ShellOutputCleaner:
    """Cleans and summarizes shell output using the agent's LLM."""
    
    def __init__(self, 
                 client: Optional[LLMClient] = None,
                 max_output_length: int = 5000,
                 enabled: bool = True):
        """Initialize the output cleaner.
        
        Args:
            client: LLM client from the agent (if None, LLM processing is disabled).
            max_output_length: Maximum length of output before applying LLM processing.
            enabled: Whether output cleaning is enabled.
        """
        self.client = client
        self.max_output_length = max_output_length
        self.enabled = enabled
        self.llm_available = client is not None
    
    def clean_output(self, raw_output: str, command: str = "") -> str:
        """Clean and summarize shell output.
        
        Args:
            raw_output: Raw shell output from tmux.
            command: The command that generated this output (for context).
            
        Returns:
            Cleaned and potentially summarized output.
        """
        if not raw_output.strip():
            return raw_output
        
        # Always apply basic cleaning if enabled
        if self.enabled:
            cleaned_output = self._basic_clean(raw_output)
        else:
            cleaned_output = raw_output
        
        # If LLM is available and output is long enough, apply LLM-based processing
        if (self.enabled and self.llm_available and 
            len(cleaned_output) > self.max_output_length):
            try:
                return self._llm_process(cleaned_output, command)
            except Exception as e:
                logger.warning(f"LLM processing failed: {e}, returning basic cleaned output")
                return cleaned_output
        
        return cleaned_output
    
    def _basic_clean(self, output: str) -> str:
        """Apply basic rule-based cleaning to remove common noise."""
        if not output:
            return output
            
        lines = output.split('\n')
        cleaned_lines = []
        
        # Patterns to remove or clean
        prompt_patterns = [
            r'^root@sandbox:.*\$\s*$',  # Remove shell prompts
            r'^\(base\)\s+\w+@[\w-]+:.*\$\s*$',  # Remove conda/base prompts
            r'^\w+@[\w-]+:.*\$\s*$',  # Remove generic prompts
        ]
        
        # ANSI escape sequence pattern
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        
        prev_line = ""
        for line in lines:
            # Remove ANSI escape sequences
            clean_line = ansi_escape.sub('', line)
            
            # Skip empty lines and pure whitespace
            if not clean_line.strip():
                continue
            
            # Skip lines that match prompt patterns
            skip_line = False
            for pattern in prompt_patterns:
                if re.match(pattern, clean_line.strip()):
                    skip_line = True
                    break
            
            if skip_line:
                continue
                
            # Skip duplicate consecutive lines
            if clean_line.strip() == prev_line.strip():
                continue
                
            cleaned_lines.append(clean_line)
            prev_line = clean_line
        
        return '\n'.join(cleaned_lines).strip()
    
    def _llm_process(self, output: str, command: str) -> str:
        """Use LLM to intelligently clean and summarize the output."""
        
        # Construct prompt for LLM processing
        prompt = f"""Clean this shell command output by removing noise and keeping essential information:

COMMAND: {command}

INSTRUCTIONS:
1. Remove terminal prompts, ANSI codes, and repetitive lines
2. Keep all errors, warnings, and important results
3. For test outputs: preserve test results, failures, and error messages
4. For build outputs: preserve compilation errors, warnings, and success/failure status
5. For file operations: preserve file paths, permissions, and operation results
6. Summarize verbose logs but keep key information
7. Keep the output concise but informative
8. If there are critical errors or failures, preserve the full error messages
9. In case you know where code error file, lines report correct where the error is.
RAW OUTPUT:
{output}

CLEANED OUTPUT:"""

        try:
            # Create message for LLM
            messages: LLMMessages = [[TextPrompt(text=prompt)]]
            
            # Generate response with short token limit for conciseness
            response, _ = self.client.generate(
                messages=messages,
                max_tokens=2000,
                temperature=0.0
            )
            
            # Extract text from response
            result = ""
            for content in response:
                if isinstance(content, TextResult):
                    result += content.text
            
            return result.strip() if result.strip() else output
            
        except Exception as e:
            logger.error(f"LLM processing failed: {e}")
            raise