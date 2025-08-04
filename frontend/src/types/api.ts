/**
 * TypeScript interfaces for II Agent API integration
 * Generated based on the backend API models
 */

// Authentication types
export interface UserRegistration {
  email: string;
  username: string;
  password: string;
  first_name?: string;
  last_name?: string;
  organization?: string;
}

export interface UserLogin {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserProfile {
  id: string;
  email: string;
  username: string;
  first_name?: string;
  last_name?: string;
  role: string;
  subscription_tier: string;
  is_active: boolean;
  email_verified: boolean;
  created_at: string;
  last_login_at?: string;
  organization?: string;
  login_provider?: string;
}

export interface UserProfileUpdate {
  first_name?: string;
  last_name?: string;
  organization?: string;
}

export interface ChangePassword {
  current_password: string;
  new_password: string;
}

// Session types
export interface SessionCreate {
  name?: string;
  settings?: Record<string, any>;
  sandbox_template?: string;
}

export interface SessionUpdate {
  name?: string;
  status?: 'pending' | 'active' | 'pause';
  settings?: Record<string, any>;
  is_public?: boolean;
}

export interface SessionInfo {
  id: string;
  user_id: string;
  name?: string;
  status: string;
  sandbox_id?: string;
  workspace_dir: string;
  is_public: boolean;
  public_url?: string;
  token_usage?: Record<string, any>;
  settings?: Record<string, any>;
  created_at: string;
  updated_at?: string;
  last_message_at?: string;
  device_id?: string;
}

export interface SessionList {
  sessions: SessionInfo[];
  total: number;
  page: number;
  per_page: number;
}

export interface SessionStats {
  total_sessions: number;
  active_sessions: number;
  paused_sessions: number;
  sessions_today: number;
  sessions_this_week: number;
  sessions_this_month: number;
  total_messages: number;
  average_session_duration?: number;
}

// Sandbox types
export interface SandboxCreate {
  template?: string;
  cpu_limit?: number;
  memory_limit?: number;
  disk_limit?: number;
  network_enabled?: boolean;
  metadata?: Record<string, any>;
}

export interface SandboxInfo {
  id: string;
  provider: string;
  sandbox_id: string;
  user_id: string;
  template: string;
  status: string;
  cpu_limit: number;
  memory_limit: number;
  disk_limit: number;
  network_enabled: boolean;
  metadata?: Record<string, any>;
  created_at: string;
  started_at?: string;
  stopped_at?: string;
  last_activity_at?: string;
}

export interface SandboxCommand {
  command: string;
  timeout?: number;
  working_directory?: string;
}

export interface SandboxCommandResult {
  exit_code: number;
  stdout: string;
  stderr: string;
  execution_time: number;
  timeout: boolean;
}

export interface SandboxFile {
  path: string;
  content?: string;
  encoding?: string;
}

export interface SandboxFileInfo {
  path: string;
  size: number;
  is_directory: boolean;
  created_at: string;
  modified_at: string;
  permissions: string;
}

export interface SandboxTemplate {
  id: string;
  name: string;
  description: string;
  version: string;
  base_image: string;
  supported_languages: string[];
  default_cpu: number;
  default_memory: number;
  default_disk: number;
}

// Settings types
export interface LLMProviderCreate {
  provider: 'openai' | 'anthropic' | 'bedrock' | 'gemini' | 'azure';
  api_key: string;
  base_url?: string;
  metadata?: Record<string, any>;
}

export interface LLMProviderUpdate {
  api_key?: string;
  base_url?: string;
  is_active?: boolean;
  metadata?: Record<string, any>;
}

export interface LLMProviderInfo {
  id: string;
  provider: string;
  base_url?: string;
  is_active: boolean;
  has_api_key: boolean;
  created_at: string;
  updated_at?: string;
  metadata?: Record<string, any>;
}

export interface MCPConfigCreate {
  mcp_config: Record<string, any>;
}

export interface MCPConfigInfo {
  id: string;
  mcp_config: Record<string, any>;
  is_active: boolean;
  created_at: string;
  updated_at?: string;
}

export interface ProviderValidation {
  provider: string;
  valid: boolean;
  error_message?: string;
  supported_models?: string[];
}

// File storage types
export interface FileUploadResponse {
  file_id: string;
  file_name: string;
  file_size: number;
  content_type: string;
  storage_url: string;
  public_url?: string;
  uploaded_at: string;
}

export interface FileInfo {
  file_id: string;
  file_name: string;
  file_size: number;
  content_type: string;
  storage_url: string;
  public_url?: string;
  session_id: string;
  user_id: string;
  uploaded_at: string;
  metadata?: Record<string, any>;
}

export interface FileList {
  files: FileInfo[];
  total: number;
  page: number;
  per_page: number;
}

export interface FileShareRequest {
  file_id: string;
  expiration_hours?: number;
  allow_download?: boolean;
}

export interface FileShareResponse {
  file_id: string;
  share_url: string;
  expires_at: string;
  allow_download: boolean;
}

export interface StorageStats {
  total_files: number;
  total_size_bytes: number;
  total_size_mb: number;
  files_by_type: Record<string, number>;
  storage_used_percent: number;
  storage_limit_bytes: number;
}

// User management (admin only)
export interface UserList {
  users: UserProfile[];
  total: number;
  page: number;
  per_page: number;
}

export interface UserStats {
  total_users: number;
  active_users: number;
  verified_users: number;
  inactive_users: number;
  unverified_users: number;
  subscription_stats: Record<string, number>;
  role_stats: Record<string, number>;
}

// WebSocket message types
export enum MessageType {
  CONNECTION_ESTABLISHED = 'connection_established',
  USER_CONNECTED = 'user_connected',
  USER_DISCONNECTED = 'user_disconnected',
  CHAT_MESSAGE = 'chat_message',
  MESSAGE_RECEIVED = 'message_received',
  MESSAGE_ERROR = 'message_error',
  AGENT_RESPONSE = 'agent_response',
  AGENT_THINKING = 'agent_thinking',
  AGENT_TOOL_USE = 'agent_tool_use',
  AGENT_ERROR = 'agent_error',
  SESSION_CREATED = 'session_created',
  SESSION_UPDATED = 'session_updated',
  SESSION_PAUSED = 'session_paused',
  SESSION_RESUMED = 'session_resumed',
  FILE_UPLOADED = 'file_uploaded',
  FILE_PROCESSING = 'file_processing',
  FILE_PROCESSED = 'file_processed',
  FILE_ERROR = 'file_error',
  TYPING_INDICATOR = 'typing_indicator',
  PRESENCE_UPDATE = 'presence_update',
  SYSTEM_NOTIFICATION = 'system_notification',
  ERROR = 'error',
  PING = 'ping',
  PONG = 'pong',
}

export interface BaseMessage {
  type: MessageType;
  timestamp: string;
  session_id?: string;
  user_id?: string;
}

export interface ChatMessage extends BaseMessage {
  type: MessageType.CHAT_MESSAGE;
  content: string;
  files?: string[];
  metadata?: Record<string, any>;
}

export interface AgentResponse extends BaseMessage {
  type: MessageType.AGENT_RESPONSE;
  content: string;
  thinking_content?: string;
  tool_uses?: Array<Record<string, any>>;
  metadata?: Record<string, any>;
}

export interface AgentThinking extends BaseMessage {
  type: MessageType.AGENT_THINKING;
  thinking_content: string;
  is_complete: boolean;
}

export interface AgentToolUse extends BaseMessage {
  type: MessageType.AGENT_TOOL_USE;
  tool_name: string;
  tool_input: Record<string, any>;
  tool_output?: Record<string, any>;
  is_complete: boolean;
  error?: string;
}

export interface TypingIndicator extends BaseMessage {
  type: MessageType.TYPING_INDICATOR;
  is_typing: boolean;
  device_id?: string;
}

export interface PresenceUpdate extends BaseMessage {
  type: MessageType.PRESENCE_UPDATE;
  status: 'online' | 'away' | 'busy' | 'offline';
  device_id?: string;
}

export interface SystemNotification extends BaseMessage {
  type: MessageType.SYSTEM_NOTIFICATION;
  title: string;
  content: string;
  level: 'info' | 'warning' | 'error' | 'success';
  action_url?: string;
}

export interface ErrorMessage extends BaseMessage {
  type: MessageType.ERROR;
  error_code: string;
  error_message: string;
  details?: Record<string, any>;
}

// API Response wrapper
export interface ApiResponse<T = any> {
  data?: T;
  error?: {
    code: string;
    message: string;
    details?: Record<string, any>;
  };
  success: boolean;
}

// Connection stats
export interface ConnectionStats {
  total_connections: number;
  unique_users: number;
  active_sessions: number;
  active_last_5min: number;
  active_last_1hr: number;
  client_types: Record<string, number>;
}