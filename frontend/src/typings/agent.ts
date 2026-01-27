export enum TAB {
    CODE = 'code',
    TERMINAL = 'terminal',
    RESULT = 'result',
    BUILD = 'build'
}

export enum VIEW_MODE {
    CHAT = 'chat',
    DESIGN = 'design'
}

export enum QUESTION_MODE {
    AGENT = 'agent',
    CHAT = 'chat'
}

export const AVAILABLE_MODELS = [
    'claude-sonnet-4@20250514',
    'claude-opus-4@20250514',
    'claude-3-7-sonnet@20250219',
    'gemini-2.5-pro-preview-05-06',
    'gpt-4.1'
]

export enum WebSocketConnectionState {
    CONNECTING = 'connecting',
    CONNECTED = 'connected',
    DISCONNECTED = 'disconnected'
}

export type Source = {
    title: string
    url: string
}

export enum AgentEvent {
    AGENT_INITIALIZED = 'agent_initialized',
    USER_MESSAGE = 'user_message',
    CONNECTION_ESTABLISHED = 'connection_established',
    WORKSPACE_INFO = 'workspace_info',
    PROCESSING = 'processing',
    AGENT_THINKING = 'agent_thinking',
    TOOL_CALL = 'tool_call',
    TOOL_RESULT = 'tool_result',
    AGENT_RESPONSE = 'agent_response',
    COMPLETE = 'complete',
    ERROR = 'error',
    SYSTEM = 'system',
    PONG = 'pong',
    UPLOAD_SUCCESS = 'upload_success',
    BROWSER_USE = 'browser_use',
    FILE_EDIT = 'file_edit',
    PROMPT_GENERATED = 'prompt_generated',
    AGENT_RESPONSE_INTERRUPTED = 'agent_response_interrupted',
    STATUS_UPDATE = 'status_update',
    SANDBOX_STATUS = 'sandbox_status',
    SUB_AGENT_COMPLETE = 'sub_agent_complete',
    SUB_AGENT_INTERRUPTED = 'sub_agent_interrupted',
    TOOL_PROGRESS = 'tool_progress',
    MODEL_COMPACT = 'model_compact'
}

export enum TOOL {
    SEQUENTIAL_THINKING = 'sequential_thinking',
    MESSAGE_USER = 'message_user',
    BROWSER_USE = 'browser_use',
    PRESENTATION = 'presentation',
    WEB_SEARCH = 'web_search',
    WEB_BATCH_SEARCH = 'web_batch_search',
    IMAGE_SEARCH = 'image_search',
    VISIT = 'web_visit',
    VISIT_COMPRESS = 'web_visit_compress',
    SHELL_EXEC = 'shell_exec',
    SHELL_KILL_PROCESS = 'shell_kill_process',
    SHELL_VIEW = 'shell_view',
    SHELL_WRITE_TO_PROCESS = 'shell_write_to_process',
    SHELL_WAIT = 'shell_wait',
    FULLSTACK_PROJECT_INIT = 'fullstack_project_init',
    SAVE_CHECKPOINT = 'save_checkpoint',
    COMPLETE = 'complete',
    STATIC_DEPLOY = 'static_deploy',
    REGISTER_DEPLOYMENT = 'register_deployment',
    PDF_TEXT_EXTRACT = 'pdf_text_extract',
    AUDIO_TRANSCRIBE = 'audio_transcribe',
    GENERATE_AUDIO_RESPONSE = 'generate_audio_response',
    VIDEO_GENERATE = 'generate_video',
    LONG_VIDEO_GENERATE = 'generate_long_video_from_text',
    LONG_VIDEO_GENERATE_FROM_IMAGE = 'generate_long_video_from_image',
    IMAGE_GENERATE = 'generate_image',
    DEEP_RESEARCH = 'deep_research',
    LIST_HTML_LINKS = 'list_html_links',
    RETURN_CONTROL_TO_USER = 'return_control_to_user',
    SLIDE_DECK_INIT = 'slide_deck_init',
    SLIDE_DECK_COMPLETE = 'slide_deck_complete',
    DISPLAY_IMAGE = 'display_image',
    REVIEWER_AGENT = 'reviewer_agent',
    SUB_AGENT = 'sub_agent',
    SUB_AGENT_RESEARCHER = 'sub_agent_researcher',
    DESIGN_DOCUMENT_AGENT = 'design_document_agent',

    GET_DATABASE_CONNECTION = 'get_database_connection',
    GET_OPENAI_KEY = 'get_openai_api_key',
    // browser tools - synced with SELECTED_TOOLS in playwright.py
    BROWSER_CLICK = 'browser_click',
    BROWSER_CLOSE = 'browser_close',
    BROWSER_CONSOLE_MESSAGES = 'browser_console_messages',
    BROWSER_DRAG = 'browser_drag',
    BROWSER_EVALUATE = 'browser_evaluate',
    BROWSER_HANDLE_DIALOG = 'browser_handle_dialog',
    BROWSER_HOVER = 'browser_hover',
    BROWSER_NAVIGATE = 'browser_navigate',
    BROWSER_NETWORK_REQUESTS = 'browser_network_requests',
    BROWSER_PRESS_KEY = 'browser_press_key',
    BROWSER_SELECT_OPTION = 'browser_select_option',
    BROWSER_SNAPSHOT = 'browser_snapshot',
    BROWSER_TAKE_SCREENSHOT = 'browser_take_screenshot',
    BROWSER_TYPE = 'browser_type',
    BROWSER_WAIT_FOR = 'browser_wait_for',
    BROWSER_TAB_CLOSE = 'browser_tab_close',
    BROWSER_TAB_LIST = 'browser_tab_list',
    BROWSER_TAB_NEW = 'browser_tab_new',
    BROWSER_TAB_SELECT = 'browser_tab_select',
    BROWSER_MOUSE_CLICK_XY = 'browser_mouse_click_xy',
    BROWSER_MOUSE_DRAG_XY = 'browser_mouse_drag_xy',
    BROWSER_MOUSE_MOVE_XY = 'browser_mouse_move_xy',
    BROWSER_NAVIGATION = 'browser_navigation',
    BROWSER_WAIT = 'browser_wait',
    BROWSER_VIEW_INTERACTIVE_ELEMENTS = 'browser_view_interactive_elements',
    BROWSER_SCROLL_DOWN = 'browser_scroll_down',
    BROWSER_SCROLL_UP = 'browser_scroll_up',
    BROWSER_SWITCH_TAB = 'browser_switch_tab',
    BROWSER_OPEN_NEW_TAB = 'browser_open_new_tab',
    BROWSER_GET_SELECT_OPTIONS = 'browser_get_select_options',
    BROWSER_SELECT_DROPDOWN_OPTION = 'browser_select_dropdown_option',
    BROWSER_RESTART = 'browser_restart',
    BROWSER_ENTER_TEXT = 'browser_enter_text',
    BROWSER_ENTER_MULTI_TEXTS = 'browser_enter_multi_texts',

    TODO_WRITE = 'TodoWrite',
    TODO_READ = 'TodoRead',
    READ = 'Read',
    WRITE = 'Write',
    EDIT = 'Edit',
    LS = 'LS',
    BASH = 'Bash',
    BASH_INIT = 'BashInit',
    BASH_VIEW = 'BashView',
    BASH_STOP = 'BashStop',
    BASH_KILL = 'BashKill',
    BASH_LIST = 'BashList',
    BASH_WRITE_TO_PROCESS = 'BashWriteToProcess',
    GLOB = 'Glob',
    GREP = 'ASTGrep',
    MULTI_EDIT = 'MultiEdit',
    REGISTER_PORT = 'register_port',
    MCP_TOOL = 'mcp_tool',
    TASK = 'Task',
    SLIDE_WRITE = 'SlideWrite',
    SLIDE_EDIT = 'SlideEdit',
    READ_REMOTE_IMAGE = 'read_remote_image',
    CODEX_AGENT = 'codex_agent',
    CODEX_EXECUTE = 'codex_execute', // Legacy, kept for backward compatibility
    CODEX_REVIEW = 'codex_review', // Legacy, kept for backward compatibility
    MCP_CODEX_EXECUTE = 'mcp_codex_execute', // New MCP stdio version
    CODEX_MCP_CODEX_EXECUTE = 'mcp_codex-as-mcp_codex_execute', // New MCP stdio version
    MCP_CODEX_REVIEW = 'mcp_codex_review', // New MCP stdio version
    CODEX_MCP_CODEX_REVIEW = 'mcp_codex-as-mcp_codex_review', // New MCP stdio version
    APPLY_PATCH = 'apply_patch',
    SLIDE_APPLY_PATCH = 'slide_apply_patch',
    STR_REPLACE_BASED_EDIT = 'str_replace_based_edit_tool',
    CLAUDE_CODE = 'mcp_claude_code'
}

export type Plan = {
    id: string
    content: string
    status: 'pending' | 'in_progress' | 'completed'
}

export interface FileURLContent {
    type: 'file_url'
    url: string
    mime_type: string
    name: string
    size: number
}

export interface AgentContext {
    agentId: string
    agentType: 'main' | 'subagent'
    agentName?: string
    parentAgentId?: string
    nestingLevel: number
    startTime?: number
    endTime?: number
    status?: 'running' | 'completed' | 'failed' | 'stopped'
}

export type ActionStep = {
    type: TOOL
    data: {
        isResult?: boolean
        tool_call_id?: string
        tool_name?: string
        tool_display_name?: string
        agentContext?: AgentContext
        tool_input?: {
            description?: string
            action?: string
            text?: string
            thought?: string
            path?: string
            file_text?: string
            file_path?: string
            command?: string
            url?: string
            query?: string
            queries?: string[]
            file?: string
            instruction?: string
            output_filename?: string
            output_path?: string
            key?: string
            session_id?: string
            seconds?: number
            input?: string
            enter?: boolean
            framework?: string
            project_name?: string
            database_type?: string
            old_string?: string
            new_string?: string
            old_str?: string
            new_str?: string
            project_directory?: string
            commit_message?: string
            todos?: Plan[]
            session_names?: string[]
            session_name?: string
            press_enter?: boolean
            content?: string
            pattern?: string
            include?: string
            name?: string
            tool_name?: string
            prompt?: string
            port?: number
            element?: string
            x?: number
            y?: number
            filename?: string
            presentation_name?: string
            slide_number?: number
            enter_texts?: Array<{
                text: string
                coordinate_x: number
                coordinate_y: number
                press_enter?: boolean
            }>
            coordinate_x_start?: number
            coordinate_y_start?: number
            coordinate_x_end?: number
            coordinate_y_end?: number
            urls?: string[]
            changes?: Record<
                string,
                {
                    add: {
                        content: string
                    }
                    delete: {
                        content: string
                    }
                    update: {
                        unified_diff: string
                    }
                }
            >
        }
        result?:
            | string
            | Record<string, unknown>
            | Record<string, unknown>[]
            | FileURLContent
        query?: string
        content?: string
        path?: string
    }
}

export interface Message {
    id: string
    role: 'user' | 'assistant' | 'system'
    content?: string
    timestamp: number
    action?: ActionStep
    files?: Array<{
        id: string
        file_name: string
        file_size: number
        content_type: string
        created_at: string
    }>
    fileContents?: { [filename: string]: string } // Base64 content of files
    attachments?: Array<AttachmentMeta>
    isHidden?: boolean
    isThinkMessage?: boolean
    agentContext?: AgentContext
    subagentMessages?: Message[] // For grouping subagent messages
}

export type AttachmentType = 'code' | 'xlsx' | 'documents' | 'archive'

export interface AttachmentMeta {
    name: string
    url: string
    file_type: AttachmentType
}

export interface ISession {
    id: string
    workspace_dir: string
    created_at: string
    name: string
    agent_type: string
    is_public?: boolean
}

export interface IEvent {
    id: string
    type: AgentEvent
    content: Record<string, unknown>
    timestamp: string
    workspace_dir: string
}

export interface ToolSettings {
    deep_research: boolean
    pdf: boolean
    media_generation: boolean
    audio_generation: boolean
    browser: boolean
    thinking_tokens: number
    enable_reviewer: boolean
    design_document: boolean
    codex_tools: boolean
    claude_code: boolean
}
export interface ChatToolSettings {
    web_search: boolean
    web_visit: boolean
    image_search: boolean
    code_interpreter: boolean
}
export interface GooglePickerResponse {
    action: string
    docs?: Array<GoogleDocument>
}

export interface GoogleDocument {
    id: string
    name: string
    thumbnailUrl: string
    mimeType: string
}

export interface LLMConfig {
    api_key?: string
    model?: string
    base_url?: string
    max_retries?: string
    temperature?: string
    vertex_region?: string
    vertex_project_id?: string
    api_type?: string
    cot_model?: boolean
    azure_endpoint?: string
    azure_api_version?: string
}

export interface ISetting {
    llm_configs?: {
        [provider: string]: LLMConfig
    }
    search_config?: {
        firecrawl_api_key?: string
        firecrawl_base_url?: string
        serpapi_api_key?: string
        tavily_api_key?: string
        jina_api_key?: string
    }
    media_config?: {
        gcp_project_id?: string
        gcp_location?: string
        gcs_output_bucket?: string
        google_ai_studio_api_key?: string
    }
    audio_config?: {
        openai_api_key: string
        azure_endpoint: string
        azure_api_version: string
    }
    third_party_integration_config?: {
        neon_db_api_key: string
        openai_api_key: string
        vercel_api_key: string
    }
    sandbox_config?: {
        mode: string
        template_id: string
        sandbox_api_key: string
    }
}

export enum BUILD_STEP {
    THINKING = 'thinking',
    PLAN = 'plan',
    BUILD = 'build'
}

export interface IMCPTool {
    name: string
    author: string
    description: string
    logo: string
    url: string
    config: Record<string, unknown>
    isRequireKey?: boolean
}

export enum AGENT_TYPE {
    GENERAL = 'general',
    MEDIA = 'media',
    SLIDE = 'slide',
    WEBSITE_BUILD = 'website_build',
    CODEX = 'codex',
    CLAUDE_CODE = 'claude_code'
}

export interface PresentationListResponse {
    session_id?: string
    presentations?: {
        name?: string
        slide_count?: number
        last_updated?: string
        slides?: {
            id: string
            presentation_name?: string
            slide_number?: number
            slide_title?: string
            slide_content?: string
            session_id?: string
            metadata?: Record<string, unknown>
            created_at?: string
            updated_at?: string
        }[]
    }[]
    total?: number
}

export interface UpdateSlideRequest {
    session_id: string
    presentation_name: string
    slide_number: number
    content: string
    title: string
    description?: string
}

export interface UpdateSlideResponse {
    success: boolean
    error?: string
    error_code?: string
}
