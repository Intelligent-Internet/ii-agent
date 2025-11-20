import { db, Document } from '../db/index.js';
import { Message } from '../llm/types.js';

export interface ChatMessage {
    id?: string;
    session_id: string;
    role: string;
    content: any; // JSON blob
    created_at?: string;
}

export class ChatService {
    async addMessage(sessionId: string, message: Message) {
        // We store the raw message structure to easily reconstruct it later
        return db.create('chat_message', {
            session_id: sessionId,
            role: message.role,
            content: message // Store the full message object as content for simplicity
        });
    }

    async getHistory(sessionId: string): Promise<Message[]> {
        const docs = db.find('chat_message', (item: any) => item.session_id === sessionId);

        // Sort by created_at if needed (our simplistic DB stores insertion order usually but created_at is reliable)
        // @ts-ignore
        docs.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());

        return docs.map(doc => doc.content.content as Message);
    }
}

export const chatService = new ChatService();
