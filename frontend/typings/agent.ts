export type Source = {
  title: string;
  url: string;
};

export enum AgentEvent {
  CONNECTION_ESTABLISHED = "connection_established",
  WORKSPACE_INFO = "workspace_info",
  PROCESSING = "processing",
  AGENT_THINKING = "agent_thinking",
  TOOL_CALL = "tool_call",
  TOOL_RESULT = "tool_result",
  AGENT_RESPONSE = "agent_response",
  STREAM_COMPLETE = "stream_complete",
  ERROR = "error",
  SYSTEM = "system",
  PONG = "pong",
}

export enum TOOL {
  SEQUENTIAL_THINKING = "sequential_thinking",
  STR_REPLACE_EDITOR = "str_replace_editor",
  BROWSER_USE = "browser_use",
  TAVILY_SEARCH = "tavily_web_search",
  TAVILY_VISIT = "tavily_visit_webpage",
  BASH = "bash",
  FILE_WRITE = "file_write",
  COMPLETE = "complete",
}

export type ActionStep = {
  type: TOOL;
  data: {
    tool_name?: string;
    tool_input?: {
      thought?: string;
      path?: string;
      file_text?: string;
      command?: string;
      url?: string;
      query?: string;
      file?: string;
      instruction?: string;
    };
    result?: string | Record<string, unknown>;
    query?: string;
  };
};
