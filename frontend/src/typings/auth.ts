export interface GoogleAuthRequest {
    code: string
    redirect_uri: string
}

export interface GoogleAuthResponse {
    access_token: string
    refresh_token: string
    token_type: string
    expires_in: number
}

// Response from /auth/dev/login endpoint (same shape as GoogleAuthResponse)
export interface DevLoginResponse {
    access_token: string
    refresh_token: string
    token_type: string
    expires_in: number
}

export interface RefreshTokenResponse {
    accessToken: string
}

export interface CurrentUserResponse {
    id: string
    name: string
    email: string
    picture?: string
}
