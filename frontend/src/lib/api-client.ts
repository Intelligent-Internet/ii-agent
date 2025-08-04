/**
 * API client for II Agent backend
 * Provides typed interfaces for all backend endpoints
 */

import {
  UserRegistration,
  UserLogin,
  TokenResponse,
  UserProfile,
  UserProfileUpdate,
  ChangePassword,
  SessionCreate,
  SessionUpdate,
  SessionInfo,
  SessionList,
  SessionStats,
  SandboxCreate,
  SandboxInfo,
  SandboxCommand,
  SandboxCommandResult,
  SandboxFile,
  SandboxFileInfo,
  SandboxTemplate,
  LLMProviderCreate,
  LLMProviderUpdate,
  LLMProviderInfo,
  MCPConfigCreate,
  MCPConfigInfo,
  ProviderValidation,
  FileInfo,
  FileList,
  FileShareRequest,
  FileShareResponse,
  StorageStats,
  ApiResponse,
} from './types/api';

class ApiClient {
  private baseUrl: string;
  private token: string | null = null;

  constructor(baseUrl: string = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000') {
    this.baseUrl = baseUrl;
    this.loadToken();
  }

  private loadToken() {
    if (typeof window !== 'undefined') {
      this.token = localStorage.getItem('access_token');
    }
  }

  private saveToken(token: string) {
    this.token = token;
    if (typeof window !== 'undefined') {
      localStorage.setItem('access_token', token);
    }
  }

  private removeToken() {
    this.token = null;
    if (typeof window !== 'undefined') {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
    }
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    if (this.token) {
      headers.Authorization = `Bearer ${this.token}`;
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers,
      });

      if (response.status === 401) {
        // Token expired, try to refresh
        const refreshed = await this.refreshToken();
        if (refreshed) {
          // Retry original request
          headers.Authorization = `Bearer ${this.token}`;
          const retryResponse = await fetch(url, {
            ...options,
            headers,
          });
          const data = retryResponse.ok ? await retryResponse.json() : null;
          return {
            data,
            success: retryResponse.ok,
            error: retryResponse.ok ? undefined : {
              code: retryResponse.status.toString(),
              message: retryResponse.statusText,
            },
          };
        } else {
          // Refresh failed, redirect to login
          this.removeToken();
          throw new Error('Authentication failed');
        }
      }

      const data = response.ok ? await response.json() : null;
      return {
        data,
        success: response.ok,
        error: response.ok ? undefined : {
          code: response.status.toString(),
          message: response.statusText,
        },
      };
    } catch (error) {
      return {
        success: false,
        error: {
          code: 'NETWORK_ERROR',
          message: error instanceof Error ? error.message : 'Unknown error',
        },
      };
    }
  }

  private async refreshToken(): Promise<boolean> {
    const refreshToken = typeof window !== 'undefined' 
      ? localStorage.getItem('refresh_token') 
      : null;
    
    if (!refreshToken) return false;

    try {
      const response = await fetch(`${this.baseUrl}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (response.ok) {
        const tokens: TokenResponse = await response.json();
        this.saveToken(tokens.access_token);
        return true;
      }
      return false;
    } catch {
      return false;
    }
  }

  // Authentication endpoints
  async register(userData: UserRegistration): Promise<ApiResponse<TokenResponse>> {
    return this.request('/auth/register', {
      method: 'POST',
      body: JSON.stringify(userData),
    });
  }

  async login(credentials: UserLogin): Promise<ApiResponse<TokenResponse>> {
    const response = await this.request<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(credentials),
    });

    if (response.success && response.data) {
      this.saveToken(response.data.access_token);
      if (typeof window !== 'undefined') {
        localStorage.setItem('refresh_token', response.data.refresh_token);
      }
    }

    return response;
  }

  async logout(): Promise<void> {
    await this.request('/auth/logout', { method: 'POST' });
    this.removeToken();
  }

  async getCurrentUser(): Promise<ApiResponse<UserProfile>> {
    return this.request('/auth/me');
  }

  async updateProfile(profileData: UserProfileUpdate): Promise<ApiResponse<UserProfile>> {
    return this.request('/auth/me', {
      method: 'PUT',
      body: JSON.stringify(profileData),
    });
  }

  async changePassword(passwordData: ChangePassword): Promise<ApiResponse<void>> {
    return this.request('/auth/change-password', {
      method: 'POST',
      body: JSON.stringify(passwordData),
    });
  }

  // Session endpoints
  async createSession(sessionData: SessionCreate): Promise<ApiResponse<SessionInfo>> {
    return this.request('/sessions', {
      method: 'POST',
      body: JSON.stringify(sessionData),
    });
  }

  async listSessions(page = 1, perPage = 20, status?: string): Promise<ApiResponse<SessionList>> {
    const params = new URLSearchParams({
      page: page.toString(),
      per_page: perPage.toString(),
    });
    if (status) params.append('status', status);

    return this.request(`/sessions?${params}`);
  }

  async getSession(sessionId: string): Promise<ApiResponse<SessionInfo>> {
    return this.request(`/sessions/${sessionId}`);
  }

  async updateSession(sessionId: string, sessionData: SessionUpdate): Promise<ApiResponse<SessionInfo>> {
    return this.request(`/sessions/${sessionId}`, {
      method: 'PATCH',
      body: JSON.stringify(sessionData),
    });
  }

  async deleteSession(sessionId: string): Promise<ApiResponse<void>> {
    return this.request(`/sessions/${sessionId}`, { method: 'DELETE' });
  }

  async pauseSession(sessionId: string): Promise<ApiResponse<void>> {
    return this.request(`/sessions/${sessionId}/pause`, { method: 'POST' });
  }

  async resumeSession(sessionId: string): Promise<ApiResponse<void>> {
    return this.request(`/sessions/${sessionId}/resume`, { method: 'POST' });
  }

  async getSessionStats(): Promise<ApiResponse<SessionStats>> {
    return this.request('/sessions/stats/overview');
  }

  // Sandbox endpoints
  async createSandbox(sandboxData: SandboxCreate): Promise<ApiResponse<SandboxInfo>> {
    return this.request('/sandboxes', {
      method: 'POST',
      body: JSON.stringify(sandboxData),
    });
  }

  async listSandboxes(status?: string): Promise<ApiResponse<SandboxInfo[]>> {
    const params = status ? `?status=${status}` : '';
    return this.request(`/sandboxes${params}`);
  }

  async getSandbox(sandboxId: string): Promise<ApiResponse<SandboxInfo>> {
    return this.request(`/sandboxes/${sandboxId}`);
  }

  async startSandbox(sandboxId: string): Promise<ApiResponse<void>> {
    return this.request(`/sandboxes/${sandboxId}/start`, { method: 'POST' });
  }

  async stopSandbox(sandboxId: string): Promise<ApiResponse<void>> {
    return this.request(`/sandboxes/${sandboxId}/stop`, { method: 'POST' });
  }

  async deleteSandbox(sandboxId: string): Promise<ApiResponse<void>> {
    return this.request(`/sandboxes/${sandboxId}`, { method: 'DELETE' });
  }

  async executeCommand(sandboxId: string, command: SandboxCommand): Promise<ApiResponse<SandboxCommandResult>> {
    return this.request(`/sandboxes/${sandboxId}/execute`, {
      method: 'POST',
      body: JSON.stringify(command),
    });
  }

  async listSandboxFiles(sandboxId: string, path = '/'): Promise<ApiResponse<SandboxFileInfo[]>> {
    return this.request(`/sandboxes/${sandboxId}/files?path=${encodeURIComponent(path)}`);
  }

  async readSandboxFile(sandboxId: string, path: string): Promise<ApiResponse<{ path: string; content: string }>> {
    return this.request(`/sandboxes/${sandboxId}/files/read?path=${encodeURIComponent(path)}`);
  }

  async writeSandboxFile(sandboxId: string, fileData: SandboxFile): Promise<ApiResponse<void>> {
    return this.request(`/sandboxes/${sandboxId}/files/write`, {
      method: 'POST',
      body: JSON.stringify(fileData),
    });
  }

  async getSandboxTemplates(): Promise<ApiResponse<SandboxTemplate[]>> {
    return this.request('/sandboxes/templates');
  }

  // Settings endpoints
  async listLLMProviders(): Promise<ApiResponse<{ providers: LLMProviderInfo[] }>> {
    return this.request('/v2/settings/llm-providers');
  }

  async createLLMProvider(providerData: LLMProviderCreate): Promise<ApiResponse<LLMProviderInfo>> {
    return this.request('/v2/settings/llm-providers', {
      method: 'POST',
      body: JSON.stringify(providerData),
    });
  }

  async updateLLMProvider(providerId: string, providerData: LLMProviderUpdate): Promise<ApiResponse<LLMProviderInfo>> {
    return this.request(`/v2/settings/llm-providers/${providerId}`, {
      method: 'PATCH',
      body: JSON.stringify(providerData),
    });
  }

  async deleteLLMProvider(providerId: string): Promise<ApiResponse<void>> {
    return this.request(`/v2/settings/llm-providers/${providerId}`, { method: 'DELETE' });
  }

  async testAPIKey(provider: string, apiKey: string, baseUrl?: string): Promise<ApiResponse<ProviderValidation>> {
    return this.request('/v2/settings/llm-providers/test', {
      method: 'POST',
      body: JSON.stringify({ provider, api_key: apiKey, base_url: baseUrl }),
    });
  }

  async listMCPConfigs(): Promise<ApiResponse<{ configurations: MCPConfigInfo[] }>> {
    return this.request('/v2/settings/mcp-configs');
  }

  async createMCPConfig(configData: MCPConfigCreate): Promise<ApiResponse<MCPConfigInfo>> {
    return this.request('/v2/settings/mcp-configs', {
      method: 'POST',
      body: JSON.stringify(configData),
    });
  }

  async updateMCPConfig(configId: string, configData: Partial<MCPConfigCreate>): Promise<ApiResponse<MCPConfigInfo>> {
    return this.request(`/v2/settings/mcp-configs/${configId}`, {
      method: 'PATCH',
      body: JSON.stringify(configData),
    });
  }

  async deleteMCPConfig(configId: string): Promise<ApiResponse<void>> {
    return this.request(`/v2/settings/mcp-configs/${configId}`, { method: 'DELETE' });
  }

  // File storage endpoints
  async uploadFile(file: File, sessionId: string, makePublic = false): Promise<ApiResponse<any>> {
    const formData = new FormData();
    formData.append('file', file);

    return this.request(`/files/upload?session_id=${sessionId}&make_public=${makePublic}`, {
      method: 'POST',
      body: formData,
      headers: {}, // Let browser set Content-Type for FormData
    });
  }

  async listFiles(sessionId?: string, page = 1, perPage = 20): Promise<ApiResponse<FileList>> {
    const params = new URLSearchParams({
      page: page.toString(),
      per_page: perPage.toString(),
    });
    if (sessionId) params.append('session_id', sessionId);

    return this.request(`/files?${params}`);
  }

  async downloadFile(fileId: string): Promise<Response> {
    const response = await fetch(`${this.baseUrl}/files/${fileId}/download`, {
      headers: this.token ? { Authorization: `Bearer ${this.token}` } : {},
    });
    return response;
  }

  async deleteFile(fileId: string): Promise<ApiResponse<void>> {
    return this.request(`/files/${fileId}`, { method: 'DELETE' });
  }

  async shareFile(fileId: string, shareRequest: FileShareRequest): Promise<ApiResponse<FileShareResponse>> {
    return this.request(`/files/${fileId}/share`, {
      method: 'POST',
      body: JSON.stringify(shareRequest),
    });
  }

  async getStorageStats(): Promise<ApiResponse<StorageStats>> {
    return this.request('/files/stats');
  }

  // WebSocket connection
  createWebSocketConnection(sessionId?: string): WebSocket {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = this.baseUrl.replace(/^https?:\/\//, '');
    const params = new URLSearchParams();
    
    if (this.token) params.append('token', this.token);
    if (sessionId) params.append('session_uuid', sessionId);
    
    const url = `${protocol}//${host}/ws/v2?${params}`;
    return new WebSocket(url);
  }

  // Utility methods
  isAuthenticated(): boolean {
    return !!this.token;
  }

  getToken(): string | null {
    return this.token;
  }
}

// Create and export singleton instance
export const apiClient = new ApiClient();
export default apiClient;