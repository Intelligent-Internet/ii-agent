from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import UUID

import re
from ii_agent.agents.codeact import CodeActAgent
from ii_agent.controller.state import State
from ii_agent.core.config.agent_config import AgentConfig
from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.event import EventType, RealtimeEvent
from ii_agent.core.event_stream import EventStream
from ii_agent.llm import get_client
from ii_agent.llm.base import LLMClient, TextResult, ToolParam
from ii_agent.prompts.researcher_system_prompt import ConfigConstants, ResearcherConfig
from ii_agent.sub_agent.base import BaseAgentTool
from ii_agent.llm.context_manager.base import ContextManager
from ii_agent.agents.parser.researcher_parser import DeepResearchMessageParser
from ii_agent.sandbox.ii_sandbox import IISandbox
from ii_agent.sub_agent.report_builder import ReportBuilder, ReportType
from ii_tool.tools.base import BaseTool, ToolResult


class ResearcherAgent(BaseAgentTool):
    name: str = "sub_agent_researcher"
    display_name: str = "Researcher Agent"
    description: str = (
        "This is a very powerful tool that can perform deep research on a given instruction. "
        "Call this tool whenever user asks for a deep research. An advanced research agent capable of performing deep research on a given instruction. "
        "It synthesizes information, leverages external tools, and generates comprehensive reports "
        "in either 'basic' or 'advanced' formats based on user requirements. "
        "When the task is 'research', it will perform deep research on the instruction. "
        "When the task is 'finalize_report', you can provide the inputed reports files as well as the overall instruction and it will finalize the reports based on the inputed reports files and output a final report in markdown, pdf and website formats."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "enum": ["research", "finalize_report"],
                "description": "The task that the researcher agent is performing. When the task is 'research', the researcher agent will perform deep research on the instruction. When the task is 'finalize_report', the researcher agent will finalize the reports based on multiple reports.",
            },
            "instruction": {
                "type": "string",
                "description": "The instruction to perform deep research for, or the overal topic (the main questions) of the report to finalize",
            },
            "report_type": {
                "type": "string",
                "description": "The type of report to generate. Default to 'basic' unless user specified 'basic' or 'advanced'",
                "enum": ["basic", "advanced"],
            },
            "reports": {
                "type": "array",
                "description": "The paths to the reports to finalize. Only required when the task is 'finalize_report'",
                "items": {
                    "type": "string",
                    "description": "The path of the report to finalize",
                },
            },
            "output_file_name": {
                "type": "string",
                "description": "The name of the output file. Do not add extension to the file name, should seperate words with underscores.",
            },
        },
        "required": ["task", "instruction", "report_type", "output_file_name"],
    }
    read_only = True

    def __init__(
        self,
        sandbox: IISandbox,
        tools: List[BaseTool],
        context_manager: ContextManager,
        event_stream: EventStream,
        config: IIAgentConfig,
        max_turns: int = 200,
        user_client: LLMClient | None = None,
        session_id: Optional[UUID] = None,
        run_id: Optional[UUID] = None,
    ):
        self.sandbox = sandbox
        self.researcher_client = get_client(config.researcher_agent_config.researcher)
        if user_client is None:
            self.report_client = get_client(
                config.researcher_agent_config.report_builder
            )
            self.final_report_client = get_client(
                config.researcher_agent_config.final_report_builder
            )
        else:  # Use user client for report and final report
            self.report_client = user_client
            self.final_report_client = user_client
        has_tokenizer = config.researcher_agent_config.researcher.tokenizer is not None

        tool_params = [
            ToolParam(
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
            )
            for tool in tools
        ]

        agent_config = AgentConfig(
            stop_sequence=[ConfigConstants.END_CODE],
            temperature=0.6,
            max_tokens_per_turn=10000,
            tools=tool_params,
        )

        parser = DeepResearchMessageParser(tools=tool_params)
        researcher_agent = CodeActAgent(
            llm=self.researcher_client,
            config=agent_config,
            parser=parser,
            is_completion=has_tokenizer,
        )
        super().__init__(
            agent=researcher_agent,
            tools=tools,
            context_manager=context_manager,
            event_stream=event_stream,
            max_turns=max_turns,
            config=config,
            session_id=session_id,
            run_id=run_id,
        )

    async def _research(self, tool_input: dict[str, Any]) -> ToolResult:
        instruction = tool_input.get("instruction")
        report_type = tool_input.get("report_type")
        output_file_name = tool_input.get("output_file_name")

        if instruction is None:
            return ToolResult(
                llm_content="Please provide an instruction to perform deep research for",
                user_display_content="Please provide an instruction to perform deep research for",
            )

        if report_type is None:
            return ToolResult(
                llm_content="Please provide a report type",
                user_display_content="Please provide a report type",
            )
        if output_file_name is None:
            return ToolResult(
                llm_content="Please provide a name for the output file",
                user_display_content="Please provide a name for the output file",
            )

        system_prompt = ResearcherConfig().system_prompt.format(
            current_date=datetime.now(timezone.utc).isoformat(),
            available_tools=ConfigConstants.AVAILABLE_TOOLS,
        )

        agent_output = await self.controller.run_impl(
            tool_input={
                "instruction": system_prompt
                + "\n\n"
                + "The user instruction is: "
                + str(instruction),
            }
        )
        report_builder = ReportBuilder(
            client=self.report_client,
            event_stream=self.event_stream,
            session_id=self._get_session_id(),
            run_id=self._get_run_id(),
        )
        output_file_name = re.sub(r"[^\w\-_.]", "", output_file_name)
        try:
            report_output = await report_builder.build(
                query=instruction,
                state=self.controller.state,
                report_type=ReportType(report_type),
                skip_dash=False,
            )
            await self.sandbox.write_file(
                report_output, "/workspace/" + output_file_name + ".md"
            )

            return ToolResult(
                llm_content="Report generated successfully in the workspace as "
                + "`/workspace/"
                + output_file_name
                + ".md`. Please read the report in the workspace.",
                user_display_content="Report generated successfully in the workspace as "
                + "`/workspace/"
                + output_file_name
                + ".md`. Please read the report in the workspace.",
            )
        except Exception as e:
            try:
                await self.sandbox.write_file(
                    str(agent_output.llm_content),
                    "/workspace/" + output_file_name + ".md",
                )
                return ToolResult(
                    llm_content="Report generated successfully in the workspace as "
                    + "`/workspace/"
                    + output_file_name
                    + ".md`. Please read the report in the workspace.",
                    user_display_content="Report generated successfully in the workspace as "
                    + "`/workspace/"
                    + output_file_name
                    + ".md`. Please read the report in the workspace.",
                )
            except Exception as e:
                return ToolResult(
                    llm_content=f"Write this report down as a markdown file in the workspace: {str(agent_output.llm_content)}",
                    user_display_content=f"Research Completed.",
                )

    async def _finalize_report(self, tool_input: dict[str, Any]) -> ToolResult:
        instruction = tool_input.get("instruction")
        reports = tool_input.get("reports")
        output_file_name = tool_input.get("output_file_name")
        if reports is None:
            return ToolResult(
                llm_content="Please provide the list of paths of the reports to finalize",
                user_display_content="Please provide the list of paths of the reports to finalize",
            )
        if instruction is None:
            return ToolResult(
                llm_content="Please provide the overall topic (the main questions) of the report to finalize",
                user_display_content="Please provide the overall topic (the main questions) of the report to finalize",
            )
        if output_file_name is None:
            return ToolResult(
                llm_content="Please provide the name of the output file",
                user_display_content="Please provide the name of the output file",
            )
        combined_report = []
        for report in reports:
            report_content = await self.sandbox.read_file(report)
            combined_report.append(TextResult(text=str(report_content)))

        state = State()
        state.add_assistant_turn(combined_report)

        report_builder = ReportBuilder(
            client=self.report_client,
            event_stream=self.event_stream,
            session_id=self._get_session_id(),
            run_id=self._get_run_id(),
        )
        try:
            report_output = await report_builder.build(
                query=instruction,
                state=state,
                report_type=ReportType.ADVANCED,
                skip_dash=True,
            )
            # website_output = await report_builder.build_website(report_output, instruction)
            # Sanitize filename by removing invalid characters for bash
            output_file_name = re.sub(r"[^\w\-_.]", "", output_file_name)
            output_file_path = "/workspace/" + output_file_name
            await self.sandbox.write_file(report_output, output_file_path + ".md")
            # await self.sandbox.write_file(website_output, output_file_path + ".html")
            try:
                await self.sandbox.create_directory("/workspace/final_reports")
                pandoc_cmd = (
                    f"pandoc -o /workspace/final_reports/{output_file_name}.pdf "
                    f"{output_file_path}.md "
                    f"--pdf-engine=weasyprint "
                    f"--css=/app/template.css "
                    f"--table-of-contents "
                    f"--number-sections "
                    f"--highlight-style=tango"
                )
                await self.sandbox.run_cmd(pandoc_cmd)
                return ToolResult(
                    llm_content="Report generated successfully in the workspace as "
                    + "`/workspace/final_reports/"
                    + output_file_name
                    + ".pdf, `/workspace/"
                    + output_file_name
                    + ".md`. You shall read the markdown report and create a stunning html static website with tailwindcss for the user.",
                    user_display_content="Report generated successfully in the workspace as "
                    + "`/workspace/"
                    + output_file_name
                    + ".pdf`",
                )
            except Exception as e:
                return ToolResult(
                    llm_content="Report generated successfully in the workspace as "
                    + "`/workspace/"
                    + output_file_name
                    + ".md`. You shall read the markdown report and create a stunning html static website with tailwindcss for the user.",
                    user_display_content="Report generated successfully in the workspace as "
                    + "`/workspace/"
                    + output_file_name
                    + ".md`",
                )

        except Exception as e:
            return ToolResult(
                llm_content="Report failed to generate. Please read the reports and use your own judgment to finalize the report in a markdown format and save it in the workspace. Create a html report using tailwindcss and deploy it to a public url for user. Error: "
                + str(e),
                user_display_content="Report failed to generate. Please read the reports and use your own judgment to finalize the report in a markdown format and save it in the workspace. Create a html report using tailwindcss and deploy it to a public url for user. Error: "
                + str(e),
            )

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        try:
            task = tool_input.get("task")
            if task == "research":
                tool_result = await self._research(tool_input)
            elif task == "finalize_report":
                tool_result = await self._finalize_report(tool_input)
            else:
                tool_result = ToolResult(
                    llm_content="Please provide a valid task",
                    user_display_content="Please provide a valid task",
                )
            # Clear agent history after running the agent
        except Exception as e:
            tool_result = ToolResult(
                llm_content=f"The researcher agent returned the following error: {str(e)}. If the content exists risk you must do the research yourself and do not use the researcher anymore. If the error relates to your input, revise and call the tool again.",
                is_error=True,
            )

        # Agent is completed
        await self.event_stream.publish(
            RealtimeEvent(
                type=EventType.SUB_AGENT_COMPLETE,
                session_id=self._get_session_id(),
                run_id=self._get_run_id(),
                content={"text": "Sub agent completed"},
            )
        )
        await self.controller.clear()

        return tool_result

    async def execute_mcp_wrapper(
        self,
        description: str,
        prompt: str,
    ):
        return await self._mcp_wrapper(
            tool_input={
                "instruction": prompt,
                "question": prompt,
                "report_type": description,
            }
        )
