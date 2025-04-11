"""Majority Vote Ensembler Prompt"""


def build_ensembler_prompt(instruction: str, diffs: list[str]) -> str:
    prompt = f"""\

I am a software engineer. I am working on a task in my codebase. Here is the task:

<instruction>
{instruction}
</instruction>

I have generated {len(diffs)} different solutions to this task. Please evaluate each solution below. Each solution is in a <candidate_solution> tag. Along,
with each solution, there is a <candidate_explanation> tag that provides a justification for the solution, along with some additional context about it.

"""

    for i, diff in enumerate(diffs):
        prompt += f"""\

<candidate_solution index={i + 1}>
{diff}
</candidate_solution index={i + 1}>
"""

    prompt += """\

Follow these steps to pick the best solution:
1. Analyze each solution, along with its explanation, and understand what it does.
2. Compare and contrast the different approaches to the solution. Evaluate the pros and cons of each solution.
3. Pick the majority vote solution. Explicitly write the number of one example of the majority vote solution inside XML tags <solution_index>...</solution_index>. Do not put anything inside the XML tags other than the number.

"""

    return prompt
