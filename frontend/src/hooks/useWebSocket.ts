/**
 * React hook for WebSocket connection with II Agent backend
 * Provides typed WebSocket messaging and connection management
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { apiClient } from '../lib/api-client';
import {
  MessageType,
  BaseMessage,
  ChatMessage,
  AgentResponse,
  AgentThinking,
  TypingIndicator,
  PresenceUpdate,
  SystemNotification,
  ErrorMessage,
} from '../types/api';

export interface WebSocketHookOptions {
  sessionId?: string;
  autoConnect?: boolean;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  onMessage?: (message: BaseMessage) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Event) => void;
}

export interface WebSocketHookReturn {
  // Connection state
  isConnected: boolean;
  isConnecting: boolean;
  connectionStatus: 'disconnected' | 'connecting' | 'connected' | 'error';
  
  // Message sending
  sendMessage: (message: Partial<BaseMessage>) => void;
  sendChatMessage: (content: string, files?: string[]) => void;
  sendTypingIndicator: (isTyping: boolean) => void;
  sendPresenceUpdate: (status: 'online' | 'away' | 'busy' | 'offline') => void;
  
  // Connection management
  connect: () => void;
  disconnect: () => void;
  reconnect: () => void;
  
  // Message history
  messages: BaseMessage[];
  clearMessages: () => void;
  
  // Statistics
  stats: {
    messagesReceived: number;
    messagesSent: number;
    reconnectAttempts: number;
    lastConnected?: Date;
    lastDisconnected?: Date;
  };
}

export function useWebSocket(options: WebSocketHookOptions = {}): WebSocketHookReturn {
  const {
    sessionId,
    autoConnect = true,
    reconnectInterval = 5000,
    maxReconnectAttempts = 10,
    onMessage,
    onConnect,
    onDisconnect,
    onError,
  } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'disconnected' | 'connecting' | 'connected' | 'error'>('disconnected');
  const [messages, setMessages] = useState<BaseMessage[]>([]);
  const [stats, setStats] = useState({
    messagesReceived: 0,
    messagesSent: 0,
    reconnectAttempts: 0,
    lastConnected: undefined as Date | undefined,
    lastDisconnected: undefined as Date | undefined,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const shouldReconnectRef = useRef(true);

  const clearReconnectTimeout = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return; // Already connected
    }

    if (!apiClient.isAuthenticated()) {
      console.warn('Cannot connect WebSocket: not authenticated');
      return;
    }

    setIsConnecting(true);
    setConnectionStatus('connecting');
    clearReconnectTimeout();

    try {
      const ws = apiClient.createWebSocketConnection(sessionId);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        setIsConnecting(false);
        setConnectionStatus('connected');
        reconnectAttemptsRef.current = 0;
        setStats(prev => ({
          ...prev,
          lastConnected: new Date(),
        }));
        onConnect?.();
      };

      ws.onmessage = (event) => {
        try {
          const messageData = JSON.parse(event.data);
          const message: BaseMessage = {
            type: messageData.type,
            timestamp: messageData.timestamp || new Date().toISOString(),
            session_id: messageData.session_id,
            user_id: messageData.user_id,
            ...messageData,
          };

          setMessages(prev => [...prev, message]);
          setStats(prev => ({
            ...prev,
            messagesReceived: prev.messagesReceived + 1,
          }));

          onMessage?.(message);

          // Handle specific message types
          handleIncomingMessage(message);
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };

      ws.onclose = (event) => {
        setIsConnected(false);
        setIsConnecting(false);
        setConnectionStatus('disconnected');
        setStats(prev => ({
          ...prev,
          lastDisconnected: new Date(),
        }));
        wsRef.current = null;
        onDisconnect?.();

        // Attempt reconnection if enabled and not manually disconnected
        if (shouldReconnectRef.current && reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectAttemptsRef.current++;
          setStats(prev => ({
            ...prev,
            reconnectAttempts: prev.reconnectAttempts + 1,
          }));

          console.log(`WebSocket reconnect attempt ${reconnectAttemptsRef.current}/${maxReconnectAttempts}`);
          
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, reconnectInterval);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setConnectionStatus('error');
        onError?.(error);
      };

    } catch (error) {
      console.error('Error creating WebSocket connection:', error);
      setIsConnecting(false);
      setConnectionStatus('error');
    }
  }, [sessionId, maxReconnectAttempts, reconnectInterval, onConnect, onDisconnect, onError, onMessage, clearReconnectTimeout]);

  const disconnect = useCallback(() => {
    shouldReconnectRef.current = false;
    clearReconnectTimeout();
    
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    
    setIsConnected(false);
    setIsConnecting(false);
    setConnectionStatus('disconnected');
  }, [clearReconnectTimeout]);

  const reconnect = useCallback(() => {
    disconnect();
    shouldReconnectRef.current = true;
    reconnectAttemptsRef.current = 0;
    setTimeout(connect, 100);
  }, [connect, disconnect]);

  const sendMessage = useCallback((message: Partial<BaseMessage>) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.warn('Cannot send message: WebSocket not connected');
      return;
    }

    const fullMessage = {
      timestamp: new Date().toISOString(),
      session_id: sessionId,
      ...message,
    };

    try {
      wsRef.current.send(JSON.stringify(fullMessage));
      setStats(prev => ({
        ...prev,
        messagesSent: prev.messagesSent + 1,
      }));
    } catch (error) {
      console.error('Error sending WebSocket message:', error);
    }
  }, [sessionId]);

  const sendChatMessage = useCallback((content: string, files?: string[]) => {
    sendMessage({
      type: MessageType.CHAT_MESSAGE,
      content,
      files: files || [],
    } as ChatMessage);
  }, [sendMessage]);

  const sendTypingIndicator = useCallback((isTyping: boolean) => {
    sendMessage({
      type: MessageType.TYPING_INDICATOR,
      is_typing: isTyping,
    } as TypingIndicator);
  }, [sendMessage]);

  const sendPresenceUpdate = useCallback((status: 'online' | 'away' | 'busy' | 'offline') => {
    sendMessage({
      type: MessageType.PRESENCE_UPDATE,
      status,
    } as PresenceUpdate);
  }, [sendMessage]);

  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  const handleIncomingMessage = useCallback((message: BaseMessage) => {
    switch (message.type) {
      case MessageType.PING:
        // Respond to ping with pong
        sendMessage({ type: MessageType.PONG });
        break;
      
      case MessageType.AGENT_RESPONSE:
        // Handle agent response
        console.log('Agent response:', (message as AgentResponse).content);
        break;
      
      case MessageType.AGENT_THINKING:
        // Handle agent thinking
        console.log('Agent thinking:', (message as AgentThinking).thinking_content);
        break;
      
      case MessageType.SYSTEM_NOTIFICATION:
        // Handle system notification
        const notification = message as SystemNotification;
        console.log(`System notification [${notification.level}]:`, notification.content);
        break;
      
      case MessageType.ERROR:
        // Handle error message
        const error = message as ErrorMessage;
        console.error(`WebSocket error [${error.error_code}]:`, error.error_message);
        break;
      
      default:
        // Handle other message types
        break;
    }
  }, [sendMessage]);

  // Auto-connect on mount if enabled
  useEffect(() => {
    if (autoConnect) {
      shouldReconnectRef.current = true;
      connect();
    }

    return () => {
      shouldReconnectRef.current = false;
      disconnect();
    };
  }, [autoConnect, connect, disconnect]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearReconnectTimeout();
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [clearReconnectTimeout]);

  return {
    isConnected,
    isConnecting,
    connectionStatus,
    sendMessage,
    sendChatMessage,
    sendTypingIndicator,
    sendPresenceUpdate,
    connect,
    disconnect,
    reconnect,
    messages,
    clearMessages,
    stats,
  };
}