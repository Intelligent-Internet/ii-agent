import axiosInstance from '@/lib/axios'

export interface ChannelField {
    key: string
    label: string
    type: 'secret' | 'text' | 'number' | 'list' | 'boolean'
    env_var: string | null
    required: boolean
    has_value: boolean
    placeholder: string
    advanced: boolean
}

export interface Channel {
    name: string
    display_name: string
    icon: string
    description: string
    category: string
    difficulty: string
    setup_time: string
    quick_setup: string
    setup_type: string
    configured: boolean
    has_token: boolean
    fields: ChannelField[]
    setup_steps: string[]
    config_template: string
}

export interface ListChannelsResponse {
    source: string
    channels: Channel[]
    total: number
    configured_count: number
}

export interface ConfigureChannelRequest {
    fields: Record<string, string>
    register_webhook?: boolean
}

export interface UserChannelConfigureRequest {
    channel_type: string
    instance_name?: string  // Display name, defaults to instance_name_id
    fields: Record<string, string | number | boolean | string[]>
    agent_id?: string
    register_webhook?: boolean
}

export interface UserChannelUpdateRequest {
    instance_name?: string  // Rename display name
    enabled?: boolean
    fields?: Record<string, string | number | boolean | string[]>
    agent_id?: string
}

export interface UserChannelConfigureResponse {
    source: string
    result: unknown
    status: number
    webhook: string | null
    channel_type: string
    instance_name_id: string
    user_id: string
}

export interface UserChannelUpdateResponse {
    source: string
    result: unknown
    status: number
    instance_name_id: string
    user_id: string
}

export interface UserChannelInstance {
    instance_name_id: string  // Immutable slug ID (e.g. "my_agent_1")
    instance_name: string     // Display name (e.g. "My Agent 1")
    channel_type: string
    status: string
    config_json: Record<string, unknown>
    enabled: boolean
    agent_id: string
    created_at: string
    id: string
}

export interface ListUserChannelsResponse {
    source: string
    channels: UserChannelInstance[]
}

export interface ConfigureChannelResponse {
    source: string
    result: unknown
    status: number
    webhook: string | null
}

export interface RemoveChannelResponse {
    source: string
    result: unknown
    status: number
    webhook: string | null
}

class IIClawService {
    async listChannels(): Promise<ListChannelsResponse> {
        const response =
            await axiosInstance.get<ListChannelsResponse>('/ii-claw/channels/')
        return response.data
    }

    async getChannel(name: string): Promise<{ source: string; channel: Channel }> {
        const response = await axiosInstance.get<{
            source: string
            channel: Channel
        }>(`/ii-claw/channels/${name}`)
        return response.data
    }

    async configureChannel(
        name: string,
        req: ConfigureChannelRequest
    ): Promise<ConfigureChannelResponse> {
        const response = await axiosInstance.post<ConfigureChannelResponse>(
            `/ii-claw/channels/${name}/configure`,
            req
        )
        return response.data
    }

    async removeChannel(name: string): Promise<RemoveChannelResponse> {
        const response = await axiosInstance.delete<RemoveChannelResponse>(
            `/ii-claw/channels/${name}/configure`
        )
        return response.data
    }

    async listUserChannels(
        userId: string,
        channelType?: string
    ): Promise<UserChannelInstance[]> {
        const params = channelType ? { channel_type: channelType } : undefined
        const response = await axiosInstance.get<ListUserChannelsResponse>(
            `/ii-claw/users/${userId}/channels`,
            { params }
        )
        return response.data.channels ?? []
    }

    async removeUserChannel(
        userId: string,
        instanceNameId: string
    ): Promise<RemoveChannelResponse> {
        const response = await axiosInstance.delete<RemoveChannelResponse>(
            `/ii-claw/users/${userId}/channels/${instanceNameId}`
        )
        return response.data
    }

    async configureUserChannel(
        userId: string,
        instanceNameId: string,
        req: UserChannelConfigureRequest
    ): Promise<UserChannelConfigureResponse> {
        const response = await axiosInstance.post<UserChannelConfigureResponse>(
            `/ii-claw/users/${userId}/channels/${instanceNameId}/configure`,
            req
        )
        return response.data
    }

    async updateUserChannel(
        userId: string,
        instanceNameId: string,
        req: UserChannelUpdateRequest
    ): Promise<UserChannelUpdateResponse> {
        const response = await axiosInstance.put<UserChannelUpdateResponse>(
            `/ii-claw/users/${userId}/channels/${instanceNameId}`,
            req
        )
        return response.data
    }

    // -----------------------------------------------------------------------
    // Cron Jobs
    // -----------------------------------------------------------------------

    async listCronJobs(userId: string, label?: string): Promise<CronJob[]> {
        const params = label ? { label } : undefined
        const response = await axiosInstance.get<ListCronJobsResponse>(
            `/ii-claw/users/${userId}/cron/jobs`,
            { params }
        )
        return response.data.jobs ?? []
    }

    async createCronJob(userId: string, req: CronJobCreateRequest): Promise<unknown> {
        const response = await axiosInstance.post(
            `/ii-claw/users/${userId}/cron/jobs`,
            req
        )
        return response.data
    }

    async deleteCronJob(userId: string, jobId: string): Promise<unknown> {
        const response = await axiosInstance.delete(
            `/ii-claw/users/${userId}/cron/jobs/${jobId}`
        )
        return response.data
    }

    async toggleCronJob(userId: string, jobId: string, enabled: boolean): Promise<unknown> {
        const response = await axiosInstance.put(
            `/ii-claw/users/${userId}/cron/jobs/${jobId}/enable`,
            { enabled }
        )
        return response.data
    }

    async getCronJobHistory(userId: string, jobId: string, limit = 20): Promise<CronJobRun[]> {
        const response = await axiosInstance.get<ListCronRunsResponse>(
            `/ii-claw/users/${userId}/cron/jobs/${jobId}/history`,
            { params: { limit } }
        )
        return response.data.runs ?? []
    }

    async getAllCronHistory(userId: string, limit = 50): Promise<CronJobRun[]> {
        const response = await axiosInstance.get<ListCronRunsResponse>(
            `/ii-claw/users/${userId}/cron/history`,
            { params: { limit } }
        )
        return response.data.runs ?? []
    }

    async updateCronJob(userId: string, jobId: string, req: CronJobUpdateRequest): Promise<unknown> {
        const response = await axiosInstance.put(
            `/ii-claw/users/${userId}/cron/jobs/${jobId}`,
            req
        )
        return response.data
    }

    async testCronJob(userId: string, jobId: string): Promise<CronJobTestResponse> {
        const response = await axiosInstance.post<CronJobTestResponse>(
            `/ii-claw/users/${userId}/cron/jobs/${jobId}/test`
        )
        return response.data
    }

    // -----------------------------------------------------------------------
    // User Agents (Custom Agents)
    // -----------------------------------------------------------------------

    async listUserAgents(activeOnly = false): Promise<UserAgent[]> {
        const params = activeOnly ? { active_only: true } : undefined
        const response = await axiosInstance.get<ListUserAgentsResponse>(
            '/ii-claw/agents',
            { params }
        )
        return response.data.agents ?? []
    }

    async getUserAgent(agentId: string): Promise<UserAgent> {
        const response = await axiosInstance.get<UserAgent>(
            `/ii-claw/agents/${agentId}`
        )
        return response.data
    }

    async createUserAgent(req: UserAgentCreateRequest): Promise<UserAgent> {
        const response = await axiosInstance.post<UserAgent>(
            '/ii-claw/agents',
            req
        )
        return response.data
    }

    async updateUserAgent(agentId: string, req: UserAgentUpdateRequest): Promise<UserAgent> {
        const response = await axiosInstance.put<UserAgent>(
            `/ii-claw/agents/${agentId}`,
            req
        )
        return response.data
    }

    async deleteUserAgent(agentId: string): Promise<{ success: boolean; message: string }> {
        const response = await axiosInstance.delete<{ success: boolean; message: string }>(
            `/ii-claw/agents/${agentId}`
        )
        return response.data
    }
}

// ---------------------------------------------------------------------------
// Cron Jobs — Types
// ---------------------------------------------------------------------------

export interface CronJob {
    id: string
    name: string
    label: string | null
    enabled: boolean
    schedule_type: string
    schedule: Record<string, unknown>
    action_type: string
    action: Record<string, unknown>
    one_shot: boolean
    channel_type: Record<string, unknown> | null
    metadata: Record<string, unknown> | null
    created_at: string
    updated_at: string
}

export interface CronJobCreateRequest {
    name: string
    label?: string
    one_shot?: boolean
    schedule: Record<string, unknown>
    action: Record<string, unknown>
    channel_type?: Record<string, unknown>
    metadata?: Record<string, unknown>
}

export interface CronJobUpdateRequest {
    name: string
    label?: string
    enabled?: boolean
    one_shot?: boolean
    schedule: Record<string, unknown>
    action: Record<string, unknown>
    channel_type?: Record<string, unknown>
    metadata?: Record<string, unknown>
}

export interface CronJobTestResponse {
    source: string
    result: {
        status: string
        id: string
        name?: string
        action_type?: string
        message?: string
        error?: string
        enabled?: boolean
    }
    status: number
}

export interface CronJobRun {
    id: string
    job_id: string
    status: 'running' | 'ok' | 'error' | 'timeout'
    started_at: string
    finished_at: string | null
    duration_ms: number | null
    error_message: string | null
    action_type: string
    schedule_type: string
    metadata: Record<string, unknown> | null
}

export interface ListCronJobsResponse {
    source: string
    jobs: CronJob[]
    total: number
}

export interface ListCronRunsResponse {
    source: string
    runs: CronJobRun[]
    total: number
}

// ---------------------------------------------------------------------------
// User Agents — Types
// ---------------------------------------------------------------------------

export interface UserAgent {
    id: string
    agent_name: string
    tag: string | null
    model_id: string | null
    system_prompt: string | null
    tool_args: Record<string, unknown> | null
    skill_mode: string | null
    connector_mode: string | null
    skill_config: Record<string, unknown> | null
    connector_config: Record<string, unknown> | null
    metadata: Record<string, unknown> | null
    is_active: boolean
    created_at: string
    updated_at: string | null
}

export interface UserAgentCreateRequest {
    agent_name: string
    tag?: string
    model_id?: string
    system_prompt?: string
    tool_args?: Record<string, unknown>
    skill_mode?: string
    connector_mode?: string
    skill_config?: Record<string, unknown>
    connector_config?: Record<string, unknown>
    metadata?: Record<string, unknown>
}

export interface UserAgentUpdateRequest {
    agent_name?: string
    tag?: string
    model_id?: string
    system_prompt?: string
    tool_args?: Record<string, unknown>
    skill_mode?: string
    connector_mode?: string
    skill_config?: Record<string, unknown>
    connector_config?: Record<string, unknown>
    metadata?: Record<string, unknown>
    is_active?: boolean
}

export interface ListUserAgentsResponse {
    agents: UserAgent[]
    total: number
}

export const iiClawService = new IIClawService()
