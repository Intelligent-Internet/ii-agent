import os
from typing import Any, Dict, List

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ConfigConstants:
    """Constants used across configuration."""

    # Template fragments
    THINK_TAG_OPEN = "<think>"
    THINK_TAG_CLOSE = "</think>"
    TOOL_RESPONSE_OPEN = "<tool_response>"
    TOOL_RESPONSE_CLOSE = "</tool_response>"
    CODE_BLOCK_START = "```py"
    CODE_BLOCK_END = "```"
    END_CODE = "<end_code>"
    INSTRUCTIONS_OPEN = "<instructions>"
    INSTRUCTIONS_CLOSE = "</instructions>"

    TOOL_CALL_EXAMPLE = (
        f"{CODE_BLOCK_START}\n"
        'web_search(query="# the query to search") or '
        'visit_webpage(url="# url to visit as string")\n'
        f"{CODE_BLOCK_END}{END_CODE}"
    )

    # Stop sequences
    DEFAULT_STOP_SEQUENCE = [END_CODE]

    # Templates
    DUPLICATE_QUERY_TEMPLATE = "I have already searched for this query: {query}. Please don't search for it again."
    DUPLICATE_URL_TEMPLATE = (
        "I have already visited this url: {url}. Please don't visit it again."
    )
    SEARCH_SUFFIX = (
        "This results may not enough to provide useful information. "
        "I must do more research or use visit_webpage tool to get detailed information. \n"
    )
    VISIT_WEBPAGE_SUFFIX = (
        "I have just got some new information. Maybe it's helpful but let me see if it "
        "contains something interesting.\n"
        "I should note the interesting key ideas/ exact quote along with citations so that "
        "I can use it in the final answer.\n"
        "I can not provider the final answer when I don't have enough information or when "
        "I am not sure about the answer.\n"
    )


class LLMConfig(BaseModel):
    """Configuration for LLM clients."""

    model: str = Field(default_factory=lambda: os.getenv("R_MODEL", "r1"))
    temperature: float = Field(
        default_factory=lambda: float(os.getenv("R_TEMPERATURE", "0.2"))
    )
    top_p: float = 0.95
    presence_penalty: float = Field(
        default_factory=lambda: float(os.getenv("R_PRESENCE_PENALTY", "0"))
    )
    stop_sequence: List[str] = Field(
        default_factory=lambda: ConfigConstants.DEFAULT_STOP_SEQUENCE
    )
    api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", "empty"))
    base_url: str = Field(
        default_factory=lambda: os.getenv("OPENAI_BASE_URL", "http://localhost:4000")
    )
    report_model: str = Field(
        default_factory=lambda: os.getenv("R_REPORT_MODEL", "gpt-4o")
    )

    def get_effective_stop_sequence(self, trace_has_turns: bool = False) -> List[str]:
        """Get effective stop sequence based on state."""
        if trace_has_turns:
            # Include </think> tag as a stop token when we have turns
            return list(
                set(self.stop_sequence).union([ConfigConstants.THINK_TAG_CLOSE])
            )
        return self.stop_sequence


class AgentConfig(BaseModel):
    """Configuration for the agent."""

    llm: LLMConfig = LLMConfig()

    system_prompt: str = f"""
You are II Researcher, developed by Intelligent Internet.
You first thinks about the reasoning process in the mind and then provides the user with the answer. 
You are specialized in multistep reasoning.
Using your training data and prior lessons learned, answer the user question with absolute certainty.
To help with your reasoning, you can call tools (Python functions) directly in your thinking process
When you need more information, you can call a function like this:

{ConfigConstants.TOOL_CALL_EXAMPLE}
YOU MUST FOLLOW THE FUNCTION CALLING FORMAT STRICTLY and end the function call with {ConfigConstants.END_CODE}

I will execute this code and provide you with the result in the format:
{ConfigConstants.TOOL_RESPONSE_OPEN}
result goes here
{ConfigConstants.TOOL_RESPONSE_CLOSE}

You can then continue your reasoning based on this new information.

For example:
{ConfigConstants.TOOL_CALL_EXAMPLE}

IMPORTANT: 
    - Do not make any assumptions, if you are not sure about the answer, you can perform an action to get more information.
    - All the function calls MUST happen before the {ConfigConstants.THINK_TAG_CLOSE} tag. Only use {ConfigConstants.THINK_TAG_CLOSE} tag when you are sure about the answer.
    - All the information you claim MUST be supported by the search results if it's come from your reasoning process. Perform action to confirm your claims.
    - Research DETAILS and THOROUGHLY about the topic before you provide the final answer.
    - After the {ConfigConstants.THINK_TAG_CLOSE} tag, You can only provide the final answer.
    - The final answer should be a very detail report with citations in markdown format that contains a table if suitable.

{{available_tools}}

Current date: {{current_date}}
Now Begin! If you solve the task correctly, you will receive a reward of $1,000,000.
"""

    instructions: str = f"""
I'm remembering that the user asked me to follow these instructions:
{ConfigConstants.INSTRUCTIONS_OPEN}
* Current date: {{current_date}}

*   Don't rely only on your reasoning process, when you confused, you can perform an action to get more information.
*   Do not make any assumptions, if you are not sure about the answer, you can perform an action to get more information.
*   Every part of the answer should be supported by the search results.
*   All the information you claim MUST be supported by the search results if it's come from your reasoning process. Perform action to confirm your claims.

*   All the function calls MUST happen before the {ConfigConstants.THINK_TAG_CLOSE} tag. Only use {ConfigConstants.THINK_TAG_CLOSE} tag when you are SURE about the answer.
*   Research DETAILS and THOROUGHLY about the topic before you provide the final answer.
*   After the {ConfigConstants.THINK_TAG_CLOSE} tag, You can only provide the final answer. Only provide the final answer when you are sure about the answer or when you think that you CAN NOT answer. 
*   After several failed attemps, you should think out of the box and come with a new strategy to answer the question.
*   When you are not sure about the answer, You don't make a guess

*   The final answer should be a very detail report with citations in markdown format that contains a table if suitable.

*  When you need more information, you can call a function like this:
{ConfigConstants.CODE_BLOCK_START}
web_search(query="# the query to search") or visit_webpage(url="# url to visit as string")
{ConfigConstants.CODE_BLOCK_END}{ConfigConstants.END_CODE}
{{available_tools}}
{ConfigConstants.INSTRUCTIONS_CLOSE}

I just got some new information.
"""

    # Use constants for repeated strings
    duplicate_query_template: str = ConfigConstants.DUPLICATE_QUERY_TEMPLATE
    duplicate_url_template: str = ConfigConstants.DUPLICATE_URL_TEMPLATE


class ReportConfig(BaseModel):
    llm: LLMConfig = LLMConfig()

    # Report system prompt (separate to avoid mixing with main prompt)

    def generate_introduction_messages(
        self, trace: str, query: str
    ) -> List[Dict[str, Any]]:
        introduction_prompt = f"""{trace}\n 
Using the above latest information, Prepare a detailed report introduction on the topic -- {query}.
- The introduction should be succinct, well-structured, informative with markdown syntax.
- As this introduction will be part of a larger report, do NOT include any other sections, which are generally present in a report.
- The introduction should be preceded by an H1 heading with a suitable topic for the entire report.
- You must use in-text citation references in apa format and make it with markdown hyperlink placed at the end of the sentence or paragraph that references them like this: ([in-text citation](url)).
Assume that the current date is {datetime.now(timezone.utc).strftime("%B %d, %Y")} if required.
- The output must be written in the same language as the main topic.
"""
        return [
            {
                "role": "system",
                "content": "You are a professional writer. Please write a detailed report introduction on the topic.",
            },
            {
                "role": "user",
                "content": introduction_prompt,
            },
        ]

    def generate_subtopics_messages(
        self, trace: str, query: str
    ) -> List[Dict[str, Any]]:
        subtopics_prompt = f"""
            Provided the main topic:

            {query}

            and research data:

            {trace}

            - Construct a list of subtopics which indicate the headers of a report document to be generated on the task. 
            - There should NOT be any duplicate subtopics.
            - Limit the number of subtopics from 2 to 7
            - Finally order the subtopics by their tasks, in a relevant and meaningful order which is presentable in a detailed report
            - The subtopics must be written in the same language as the main topic.

            "IMPORTANT!":
            - Every subtopic MUST be relevant to the main topic and provided research data ONLY!
            """
        return [
            {
                "role": "system",
                "content": "You are a professional writer. Please generate a list of subtopics that can answer the main topic and relevant to the provided research data.",
            },
            {
                "role": "user",
                "content": subtopics_prompt,
            },
        ]

    def generate_subtopic_report_messages(
        self,
        trace: str,
        content_from_previous_subtopics: str,
        subtopics: List[str],
        current_subtopic: str,
        query: str,
    ) -> List[Dict[str, Any]]:
        subtopic_report_prompt = f"""
Context:
"{trace}"

Content from previous subtopics:
{content_from_previous_subtopics}

Main Topic and Subtopic:
Using the latest information available, you are constructing a detailed report on the subtopics: {subtopics} to answer the main topic: {query}. You are currently writing the report on the subtopic: {current_subtopic}.
You must limit the number of subsections to a maximum of 3

Content Focus:
- The report should focus on answering the question, be well-structured, informative, in-depth, and include facts and numbers if available.
- Use markdown syntax and follow the APA format.
- When presenting data, comparisons, or structured information, use markdown tables to enhance readability.

IMPORTANT:Content and Sections Uniqueness:
- This part of the instructions is crucial to ensure the content is unique and does not overlap with existing reports.
- Carefully review the existing headers and existing written contents provided below before writing any new subsections.
- Prevent any content that is already covered in the existing written contents.
- Do not use any of the existing headers as the new subsection headers.
- Do not repeat any information already covered in the existing written contents or closely related variations to avoid duplicates.
- If you have nested subsections, ensure they are unique and not covered in the existing written contents.
- Ensure that your content is entirely new and does not overlap with any information already covered in the previous subtopic reports.
- Your report must be written in the same language as the main topic and subtopic

- All the available topics are:

    {subtopics}

"Structure and Formatting":
- As this sub-report will be part of a larger report, include only the main body divided into suitable subtopics without any introduction or conclusion section.

- You MUST include markdown hyperlinks to relevant source URLs wherever referenced in the report, for example:

    ### Section Header
    
    This is a sample text ([in-text citation](url)).

- Use H2 for the main subtopic header (##) and H3 for subsections (###).
- Use smaller Markdown headers (e.g., H2 or H3) for content structure, avoiding the largest header (H1) as it will be used for the larger report's heading.
- Organize your content into distinct sections that build on top of each other and complement but do not overlap with existing subtopic reports.
- When adding similar or identical subsections to your report, you should clearly indicate the differences between and the new content and the existing written content from previous subtopic reports. For example:

    ### New header (similar to existing header)

    While the previous section discussed [topic A], this section will explore [topic B]."

"Date":
Assume the current date is {datetime.now(timezone.utc).strftime("%B %d, %Y")} if required.

"IMPORTANT!":
- You must focus on your designated subtopic only. Each subtopic should build on the previous subtopic but do not repeat the same key information.
- The focus MUST be on the main topic! You MUST Leave out any information un-related to it!
- Must NOT have any introduction, conclusion, summary or reference section.
- You MUST use in-text citation references in APA format and make it with markdown hyperlink placed at the end of the sentence or paragraph that references them like this: ([in-text citation](url)).
- You MUST mention the difference between the existing content and the new content in the report if you are adding the similar or same subsections wherever necessary.

Do NOT add a conclusion section.
"""
        return [
            {
                "role": "system",
                "content": "You are a professional writer. Please write a detailed report on the subtopic.",
            },
            {
                "role": "user",
                "content": subtopic_report_prompt,
            },
        ]

    def generate_report_messages(self, trace: str, query: str) -> List[Dict[str, Any]]:
        report_system_prompt: str = """
You are a specialized document structuring assistant from II AI. Your task is to analyze a main topic and supporting research data, then generate a comprehensive report.
 
All the report should be focused on answering the original question, should be well structured, informative, in-depth, and comprehensive, with facts and numbers if available and at least 1000 words.
You should strive to write the report as long as you can using all relevant and necessary information provided.

Please follow all of the following guidelines in your report:
- You MUST determine your own concrete and valid opinion based on the given information. Do NOT defer to general and meaningless conclusions.
- You MUST write the report with markdown syntax and apa format.
- You MUST prioritize the relevance, reliability, and significance of the sources you use. Choose trusted sources over less reliable ones.
- You must also prioritize new articles over older articles if the source can be trusted.
- Use in-text citation references in apa format and make it with markdown hyperlink placed at the end of the sentence or paragraph that references them like this: ([in-text citation](url)).
- For all references, use the exact url as provided in the visited URLs sections.
- The report language must be written in the same language as the main topic

You MUST write all used source urls at the end of the report as references, and make sure to not add duplicated sources, but only one reference for each.
Additionally, you MUST include hyperlinks to the relevant URLs wherever they are referenced in the report: 

eg: Author, A. A. (Year, Month Date). Title of web page. Website Name. [website](url)

The report should include:

MAIN CONTENT:
- Comprehensive analysis supported by search data
- Relevant statistics, metrics, or data points when available
- Information presented in appropriate formats (tables, lists, paragraphs) based on content type
- Evaluation of source reliability and information quality
- Key insights that directly address the original question
- Any limitations in the search or areas requiring further investigation
- Citations for all referenced information

VISUAL PRESENTATION:
- EXACTLY one well-structured table to present key data clearly
- Use consistent formatting with clear headers and aligned columns
- Include explanatory notes below the table when necessary
- Format data appropriately (correct units, significant figures, etc.) in markdown format

FINAL SYNTHESIS:
- Key findings synthesis
- Evidence-based comprehensive conclusions
- Clear connection between findings and the original question

Every section must be directly relevant to the main topic and supported by the provided research data only.
The structure should be well-organized but natural, avoiding formulaic headings or numbered sections.
The response format is in well markdown.
"""
        return [
            {
                "role": "system",
                "content": report_system_prompt,
            },
            {
                "role": "user",
                "content": f"""Here is the research process and findings:

                ### Research Process
                {trace}

                ### Original Question
                {query}

                Based on the research above, please provide a clear and comprehensive report.
                """,
            },
        ]


# Create a singleton config instance
CONFIG = AgentConfig()
REPORT_CONFIG = ReportConfig()


def get_report_config() -> ReportConfig:
    """Get the report configuration."""
    return REPORT_CONFIG


def get_config() -> AgentConfig:
    """Get the agent configuration."""
    return CONFIG


def update_config(updates: Dict[str, Any]) -> None:
    """Update the agent configuration."""
    for key, value in updates.items():
        if hasattr(CONFIG, key):
            setattr(CONFIG, key, value)
