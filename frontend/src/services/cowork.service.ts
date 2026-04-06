import { invoke } from '@tauri-apps/api/core'
import { open } from '@tauri-apps/plugin-dialog'
import type {
    CoworkChatScope,
    CoworkChatSendMessageRequest,
    CoworkChatSendMessageResponse,
    CoworkChatSessionDetail,
    CoworkChatSessionSummary,
    CoworkOrganizeTreeNode,
    CoworkOrganizeTreePair
} from '@/typings/cowork'

const HOMEPAGE_SCOPE: CoworkChatScope = 'homepage'
const ORGANIZE_SCOPE: CoworkChatScope = 'organize-file-folder'

interface ReadPathTreeOptions {
    max_depth?: number
    max_entries?: number
    include_hidden?: boolean
}

class CoworkService {
    async pickFolderPath(defaultPath?: string): Promise<string | null> {
        const selectedPath = await open({
            directory: true,
            multiple: false,
            recursive: true,
            title: 'Choose a source folder',
            defaultPath: defaultPath?.trim() || undefined
        })

        if (Array.isArray(selectedPath)) {
            return selectedPath[0] ?? null
        }

        return selectedPath ?? null
    }

    async readPathTree(
        path: string,
        options?: ReadPathTreeOptions
    ): Promise<CoworkOrganizeTreeNode> {
        return invoke<CoworkOrganizeTreeNode>('read_path_tree', {
            path,
            options
        })
    }

    async createOrganizeSession(
        treePair: CoworkOrganizeTreePair
    ): Promise<CoworkChatSessionDetail> {
        return invoke<CoworkChatSessionDetail>('create_organize_session', {
            treePair
        })
    }

    async createHomepageChatSession(
        title: string
    ): Promise<CoworkChatSessionDetail> {
        return invoke<CoworkChatSessionDetail>('create_homepage_chat_session', {
            title
        })
    }

    async updateOrganizeSession(
        session: CoworkChatSessionDetail
    ): Promise<CoworkChatSessionDetail> {
        return invoke<CoworkChatSessionDetail>('update_organize_session', {
            session
        })
    }

    async updateHomepageChatSession(
        session: CoworkChatSessionDetail
    ): Promise<CoworkChatSessionDetail> {
        return invoke<CoworkChatSessionDetail>('update_homepage_chat_session', {
            session
        })
    }

    async renameHomepageChatSession(
        sessionId: string,
        title: string
    ): Promise<CoworkChatSessionDetail> {
        return invoke<CoworkChatSessionDetail>('rename_homepage_chat_session', {
            sessionId,
            title
        })
    }

    async deleteHomepageChatSession(sessionId: string): Promise<void> {
        return invoke<void>('delete_homepage_chat_session', {
            sessionId
        })
    }

    async renameOrganizeSession(
        sessionId: string,
        title: string
    ): Promise<CoworkChatSessionDetail> {
        return invoke<CoworkChatSessionDetail>('rename_organize_session', {
            sessionId,
            title
        })
    }

    async deleteOrganizeSession(sessionId: string): Promise<void> {
        return invoke<void>('delete_organize_session', {
            sessionId
        })
    }

    async getChatSessions(
        scope: CoworkChatScope
    ): Promise<CoworkChatSessionSummary[]> {
        if (scope === HOMEPAGE_SCOPE) {
            return invoke<CoworkChatSessionSummary[]>(
                'list_homepage_chat_sessions'
            )
        }

        if (scope === ORGANIZE_SCOPE) {
            return invoke<CoworkChatSessionSummary[]>('list_organize_sessions')
        }

        return []
    }

    async getChatSession(
        sessionId: string,
        scope: CoworkChatScope = HOMEPAGE_SCOPE
    ): Promise<CoworkChatSessionDetail> {
        if (scope === HOMEPAGE_SCOPE) {
            return invoke<CoworkChatSessionDetail>(
                'get_homepage_chat_session',
                {
                    sessionId
                }
            )
        }

        if (scope === ORGANIZE_SCOPE) {
            return invoke<CoworkChatSessionDetail>('get_organize_session', {
                sessionId
            })
        }

        throw new Error(`Unsupported cowork scope: ${scope}`)
    }

    async sendChatMessage(
        payload: CoworkChatSendMessageRequest
    ): Promise<CoworkChatSendMessageResponse> {
        return invoke<CoworkChatSendMessageResponse>(
            'send_cowork_chat_message',
            {
                request: {
                    ...payload,
                    session_id: payload.session_id?.trim() || null,
                    runtime_kind: payload.runtime_kind ?? 'remote'
                }
            }
        )
    }

    async stopChatSession(
        sessionId: string,
        scope: CoworkChatScope
    ): Promise<CoworkChatSessionDetail> {
        return invoke<CoworkChatSessionDetail>('stop_cowork_chat_session', {
            scope,
            sessionId
        })
    }
}

export const coworkService = new CoworkService()
