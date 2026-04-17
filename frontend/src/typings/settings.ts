import { ISetting } from './agent'

export interface SettingsResponse {
    settings: ISetting
}

export interface ValidateApiKeyRequest {
    provider: string
    apiKey: string
}

export interface ValidateApiKeyResponse {
    valid: boolean
}

/** Must match BE Provider StrEnum in settings/llm/types.py */
export type ProviderType = 'OpenAI' | 'Anthropic' | 'Google' | 'Cerebras' | 'Custom'

/** Must match BE ApiType StrEnum in settings/llm/types.py */
export type ApiType = 'vertex_ai' | 'azure' | 'bedrock'

/** Provider-specific params stored in the `configs` JSONB column. */
export interface ModelParams {
    api_type?: ApiType | null
    max_retries?: number
    max_message_chars?: number
    temperature?: number
    thinking_tokens?: number
    vertex_region?: string
    vertex_project_id?: string
    azure_endpoint?: string
    azure_api_version?: string
    cot_model?: boolean
}

export interface IModel {
    id: string
    model: string
    model_id?: string
    provider?: ProviderType
    base_url?: string
    api_key?: string
    display_name?: string
    configs?: ModelParams | null
    context_length?: number
    input_price_per_token?: number
    output_price_per_token?: number
    supports_function_calling?: boolean
    supports_vision?: boolean
    description?: string
    source?: 'user' | 'system'
    is_default?: boolean
    pricing?: {
        input_price_per_million?: number
        output_price_per_million?: number
    } | null
    created_at?: string
    updated_at?: string
}

export interface GetAvailableModelsResponse {
    models: IModel[]
}

interface MCPServerConfig {
    command?: string
    args?: string[]
    capabilities?: string[]
    env?: Record<string, string>
    url?: string
    headers?: Record<string, string>
}

interface MCPConfig {
    mcpServers?: Record<string, MCPServerConfig>
    servers?: Record<string, MCPServerConfig>
}

interface MCPMetadata {
    auth_json?: Record<string, any>
    model?: string
    apikey?: string
    model_reasoning_effort?: string
    search?: boolean
}

export interface IMcpSettings {
    id: string
    mcp_config: MCPConfig
    metadata?: MCPMetadata
    is_active?: boolean
    created_at?: string
    updated_at?: string
}

export interface UpdateMcpSettingsPayload {
    mcp_config?: MCPConfig
    is_active?: boolean
}

export interface GetMcpSettingsResponse {
    settings: IMcpSettings[]
}

// Skills types
export interface ISkill {
    id: string
    name: string
    description: string
    source: 'builtin' | 'github' | 'custom'
    source_url?: string
    is_enabled: boolean
    license?: string
    compatibility?: string
    created_at: string
    updated_at?: string
}

export interface GetSkillsResponse {
    skills: ISkill[]
    builtin_count: number
    custom_count: number
}

export interface AddGitHubSkillRequest {
    github_url: string
}

export interface ToggleSkillRequest {
    is_enabled: boolean
}
