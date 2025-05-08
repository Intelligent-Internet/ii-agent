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
  UPLOAD_SUCCESS = "upload_success",
  BROWSER_USE = "browser_use",
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
  STATIC_DEPLOY = "static_deploy",
  PDF_TEXT_EXTRACT = "pdf_text_extract",

  BROWSER_VIEW = "browser_view",
  BROWSER_NAVIGATION = "browser_navigation",
  BROWSER_RESTART = "browser_restart",
  BROWSER_WAIT = "browser_wait",
  BROWSER_SCROLL_DOWN = "browser_scroll_down",
  BROWSER_SCROLL_UP = "browser_scroll_up",
  BROWSER_CLICK = "browser_click",
  BROWSER_ENTER_TEXT = "browser_enter_text",
  BROWSER_PRESS_KEY = "browser_press_key",
  BROWSER_GET_SELECT_OPTIONS = "browser_get_select_options",
  BROWSER_SELECT_DROPDOWN_OPTION = "browser_select_dropdown_option",
  BROWSER_SWITCH_TAB = "browser_switch_tab",
  BROWSER_OPEN_NEW_TAB = "browser_open_new_tab",
  AUDIO_TRANSCRIBE = "audio_transcribe",
  GENERATE_AUDIO_RESPONSE = "generate_audio_response",
}

export type ActionStep = {
  type: TOOL;
  data: {
    isResult?: boolean;
    tool_name?: string;
    tool_input?: {
      thought?: string;
      path?: string;
      file_text?: string;
      file_path?: string;
      command?: string;
      url?: string;
      query?: string;
      file?: string;
      instruction?: string;
      output_filename?: string;
    };
    result?: string | Record<string, unknown>;
    query?: string;
  };
};
