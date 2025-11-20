import { FastifyReply } from 'fastify';
import { Socket } from 'socket.io';

// Standard event types matching Frontend expectation
export type AgentEvent =
  | { type: 'session'; data: any }
  | { type: 'thinking'; status: 'start' | 'delta' | 'stop'; delta?: string; signature?: string }
  | { type: 'content'; status: 'start' | 'delta' | 'stop'; delta?: string }
  | { type: 'tool_call'; status: 'start' | 'delta' | 'stop'; id: string; name: string; type?: string; delta?: string; input?: string }
  | { type: 'tool_result'; status: 'info'; tool_call_id: string; name: string; output: string; is_error?: boolean }
  | { type: 'complete'; status: 'done'; message_id?: string; finish_reason?: string; elapsed_ms?: number }
  | { type: 'error'; message: string }
  | { type: 'done' };

export interface StreamAdapter {
  emit(event: AgentEvent): void;
  close(): void;
}

export class SSEStreamAdapter implements StreamAdapter {
  private reply: FastifyReply;

  constructor(reply: FastifyReply) {
    this.reply = reply;
    // Set headers for SSE
    this.reply.raw.setHeader('Content-Type', 'text/event-stream');
    this.reply.raw.setHeader('Cache-Control', 'no-cache');
    this.reply.raw.setHeader('Connection', 'keep-alive');
    this.reply.raw.flushHeaders();
  }

  emit(event: AgentEvent): void {
    // Format: event: <type>\ndata: <json>\n\n
    const eventName = event.type;
    // Frontend expects specific event names mapping to parser logic
    // Parser handles: 'session', 'thinking', 'content', 'complete', 'tool_call', 'tool_result', 'error'
    // Our `AgentEvent` types align with these.

    // Special case: 'done' is handled as [DONE] usually in OpenAI style,
    // but our frontend parser looks for `[DONE]` in raw check OR specific event types.
    // `normalizeStreamEvent` handles `[DONE]` string specifically.

    if (event.type === 'done') {
        this.reply.raw.write(`data: [DONE]\n\n`);
        return;
    }

    const { type, ...data } = event;
    this.reply.raw.write(`event: ${type}\n`);
    this.reply.raw.write(`data: ${JSON.stringify(data)}\n\n`);
  }

  close(): void {
    this.reply.raw.end();
  }
}

export class SocketStreamAdapter implements StreamAdapter {
  private socket: Socket;
  private sessionId: string;

  constructor(socket: Socket, sessionId: string) {
    this.socket = socket;
    this.sessionId = sessionId;
  }

  emit(event: AgentEvent): void {
    // Socket.IO emission
    // The frontend, if refactored for WS, would listen to 'chat_event'.
    // However, currently the frontend is SSE-only.
    // If we want Hybrid, we need to ensure the WS client on frontend (if we add one) matches this.
    // For now, we map these strict events to the legacy 'chat_event' structure used in `socket/index.ts`
    // OR we adopt this new structure for WS too.

    // Legacy `socket/index.ts` used: { type: string, content: any }
    // New structure: { type: string, ...fields }
    // We should standardise. Let's wrap it to match the generic 'chat_event' envelope
    // so the client can distinguish event types easily.

    this.socket.emit('chat_event', {
        type: event.type,
        content: event // Send full event object as content, or spread it?
        // Frontend WS implementation (if we write it) needs to parse this.
        // Let's spread it for cleaner access if possible, or keep it structured.
        // Legacy: `content` was the payload.
    });

    // Wait, let's look at the new plan's requirement: "Shared Logic: Ensure both interfaces produce identical event structures".
    // The SSE sends `event: type` and `data: JSON`.
    // The Socket should emit `type` with `JSON` payload.
    // So `socket.emit(event.type, event_data)`?
    // Or `socket.emit('stream_event', { event: type, data: event_data })`?
    // Keeping with the existing `chat_event` channel is safer for existing listeners,
    // but we are replacing the logic.
    // Let's send the exact same JSON that goes into `data` of SSE, but inside `chat_event`.

    const { type, ...data } = event;
    this.socket.emit('chat_event', {
        type: type,
        ...data
    });
  }

  close(): void {
    // No explicit close needed for Socket usually, unless we want to signal end
    this.socket.emit('chat_event', { type: 'done' });
  }
}
