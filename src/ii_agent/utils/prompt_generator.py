import logging
from typing import List, Tuple, Optional

from ii_agent.llm.base import TextPrompt, TextResult, LLMClient

# Create a logger
logger = logging.getLogger("prompt_generator")
logger.setLevel(logging.INFO)


async def enhance_user_prompt(
    client: LLMClient,
    user_input: str,
    files: List[str],
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> Tuple[bool, str, Optional[str]]:
    """
    Enhance a user request into a detailed, comprehensive prompt using an LLM.

    Args:
        client: The LLM client
        user_input: The user's request text
        files: List of file paths to include as context
        temperature: Temperature setting for generation
        max_tokens: Maximum tokens to generate

    Returns:
        Tuple of (success: bool, message: str, enhanced_prompt: Optional[str])
    """
    try:
        # Prepare context from files if provided
        file_context = ""
        if files and len(files) > 0:
            file_context = "Referenced files:\n"
            for file_path in files:
                file_path = file_path.lstrip(".")  # Remove leading dot if present
                file_context += f"- {file_path}\n"
                    
        # Generate prompt using the LLM
        system_prompt = """You are an expert at enhancing user requests into detailed, specific prompts.
Your task is to expand the user's brief request into a comprehensive prompt that will help an AI assistant understand exactly what is needed.
Include specific details, requirements, and context that would be helpful.
Format your response as a single, well-structured prompt without explanations or meta-commentary."""
        
        # Create messages in Anthropic format
        messages = [[
            TextPrompt(text=f"Enhance this request into a detailed prompt: {user_input}\n\nAdditional context - {file_context}")
        ]]
        
        # Use the Anthropic client's generate method
        response_blocks, _ = client.generate(
            messages=messages,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            temperature=temperature,
        )
        
        # Extract the generated text from the response
        enhanced_prompt = ""
        for block in response_blocks:
            if isinstance(block, TextResult):
                enhanced_prompt += block.text
        
        return True, "Prompt enhanced successfully", enhanced_prompt
        
    except Exception as e:
        logger.error(f"Error enhancing prompt: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False, f"Error enhancing prompt: {str(e)}", None
