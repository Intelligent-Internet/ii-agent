import type { ActionStep, Message } from './agent'

export type CoworkChatMessageRole = 'user' | 'assistant'
export type CoworkChatScope = 'homepage' | 'intelligent-folder'

export interface CoworkGitHubRepositoryContext {
    owner: string
    name: string
    full_name: string
    default_branch: string
}

export interface CoworkChatToolSettings {
    web_search: boolean
    web_visit: boolean
    image_search: boolean
    code_interpreter?: boolean
    generate_image?: boolean
    generate_video?: boolean
}

export interface CoworkFolderTreeNode {
    id: string
    name: string
    kind: 'folder' | 'file'
    extension?: string
    size?: string
    children?: CoworkFolderTreeNode[]
}

export interface CoworkFolderTreePair {
    source_root: string
    result_root: string
    source_tree: CoworkFolderTreeNode
    result_tree: CoworkFolderTreeNode | null
}

export interface CoworkChatMessage {
    id: string
    role: CoworkChatMessageRole
    content: string
    created_at: string
    is_think_message?: boolean
}

export interface CoworkChatSessionSummary {
    id: string
    scope: CoworkChatScope
    title: string
    preview: string
    updated_at: string
    message_count: number
}

export type CoworkChatRunStatus =
    | 'idle'
    | 'thinking'
    | 'waiting_for_input'
    | 'completed'
    | 'stopped'

export type CoworkAgentRuntimeKind = 'remote' | 'local'

export interface CoworkChatFile {
    id: string
    file_name: string
    file_size: number
    content_type: string
    created_at: string
}

export interface CoworkChatSessionDetail extends CoworkChatSessionSummary {
    runtime_kind?: CoworkAgentRuntimeKind
    runtime_session_id?: string
    messages: CoworkChatMessage[]
    runtime_events: CoworkRuntimeEventPayload[]
    files: CoworkChatFile[]
    run_status: CoworkChatRunStatus
    folder_tree_pair?: CoworkFolderTreePair
}

export type CoworkChatEvent =
    | {
          type: 'session.created' | 'session.updated'
          session: CoworkChatSessionSummary
      }
    | {
          type: 'message.created'
          scope: CoworkChatScope
          session_id: string
          message: CoworkChatMessage
      }
    | {
          type: 'files.updated'
          scope: CoworkChatScope
          session_id: string
          files: CoworkChatFile[]
      }
    | {
          type: 'status.updated'
          scope: CoworkChatScope
          session_id: string
          status: CoworkChatRunStatus
      }

export interface CoworkRuntimeEventPayload {
    type: 'runtime.event'
    scope: CoworkChatScope
    session_id: string
    runtime_event_type: string
    runtime_event_id?: string
    runtime_created_at?: string
    run_status?: string
    emitted_at: string
    content: Record<string, unknown>
}

export type CoworkChatLiveEvent = CoworkChatEvent | CoworkRuntimeEventPayload

export type CoworkLiveActivityStatus =
    | 'running'
    | 'completed'
    | 'waiting'
    | 'error'

export interface CoworkLiveToolCall {
    id: string
    name: string
    display_name: string
    input?: string
    result?: string
    status: CoworkLiveActivityStatus
    logo?: string
    skill_name?: string
    agent_name?: string
}

export interface CoworkLiveActivity {
    id: string
    runtime_event_type: string
    title: string
    detail?: string
    timestamp: string
    status?: CoworkLiveActivityStatus
    tool_call_id?: string
    tool_name?: string
    skill_name?: string
    agent_name?: string
}

export interface CoworkLiveSessionState {
    session_id: string
    scope: CoworkChatScope
    thinking: string
    response: string
    is_awaiting_turn_action?: boolean
    thinking_message_id?: string
    response_message_id?: string
    thinking_started_at?: string
    response_started_at?: string
    tool_calls: CoworkLiveToolCall[]
    activities: CoworkLiveActivity[]
    event_messages: Message[]
    current_action?: ActionStep
    last_event_at?: string
    latest_runtime_event_type?: string
}

export interface CoworkChatSendMessageRequest {
    session_id?: string | null
    runtime_kind?: CoworkAgentRuntimeKind
    scope: CoworkChatScope
    content: string
    model_id: string
    tools?: CoworkChatToolSettings
    github_repository?: CoworkGitHubRepositoryContext
}

export interface CoworkChatSendMessageResponse {
    session_id: string
    events: CoworkChatEvent[]
}
