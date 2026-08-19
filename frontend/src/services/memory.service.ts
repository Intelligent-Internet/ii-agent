import axiosInstance from '@/lib/axios'
import type {
    Memory,
    MemoryListResponse,
    MemoryCreateRequest,
    MemoryUpdateRequest
} from '@/typings/memory'

interface ListMemoriesParams {
    page?: number
    perPage?: number
    search?: string
    topics?: string
    sortBy?: 'updated_at' | 'memory' | 'topics_count'
    sortOrder?: 'asc' | 'desc'
}

class MemoryService {
    async listMemories(
        params: ListMemoriesParams = {}
    ): Promise<MemoryListResponse> {
        const response = await axiosInstance.get<MemoryListResponse>(
            '/v1/memories',
            {
                params: {
                    page: params.page ?? 1,
                    per_page: params.perPage ?? 10,
                    search: params.search || undefined,
                    topics: params.topics || undefined,
                    sort_by: params.sortBy ?? 'updated_at',
                    sort_order: params.sortOrder ?? 'desc'
                }
            }
        )
        return response.data
    }

    async getTopics(): Promise<string[]> {
        const response = await axiosInstance.get<string[]>('/v1/memories/topics')
        return response.data
    }

    async createMemory(data: MemoryCreateRequest): Promise<Memory> {
        const response = await axiosInstance.post<Memory>('/v1/memories', data)
        return response.data
    }

    async updateMemory(
        memoryId: string,
        data: MemoryUpdateRequest
    ): Promise<Memory> {
        const response = await axiosInstance.put<Memory>(
            `/v1/memories/${memoryId}`,
            data
        )
        return response.data
    }

    async deleteMemory(memoryId: string): Promise<void> {
        await axiosInstance.delete(`/v1/memories/${memoryId}`)
    }

    async bulkDeleteMemories(memoryIds: string[]): Promise<void> {
        await axiosInstance.post('/v1/memories/bulk-delete', {
            memory_ids: memoryIds
        })
    }
}

export const memoryService = new MemoryService()