"""Basic token counter for Claude."""


class ClaudeTokenCounter:
    def count_tokens(self, prompt_chars: str) -> int:
        return len(prompt_chars) // 3
