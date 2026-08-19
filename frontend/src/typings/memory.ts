export interface Memory {
    memory_id: string
    memory: string
    topics: string[] | null
    input: string | null
    agent_id: string | null
    created_at: number | null
    updated_at: number | null
}

export interface MemoryListResponse {
    memories: Memory[]
    total: number
    page: number
    per_page: number
}

export interface MemoryCreateRequest {
    memory: string
    topics?: string[]
}

export interface MemoryUpdateRequest {
    memory?: string
    topics?: string[]
}