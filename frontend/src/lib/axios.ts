import axios from 'axios'
import { clearAccessToken, getStoredAccessToken } from '@/utils/auth-token'

const axiosInstance = axios.create({
    baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
    headers: {
        'Content-Type': 'application/json'
    }
})

axiosInstance.interceptors.request.use(
    (config) => {
        const token = getStoredAccessToken()
        if (token) {
            config.headers.Authorization = `Bearer ${token}`
        }
        return config
    },
    (error) => {
        return Promise.reject(error)
    }
)

axiosInstance.interceptors.response.use(
    (response) => {
        return response
    },
    (error) => {
        if (error.response?.status === 401) {
            // Only logout if it's NOT a connector-specific endpoint
            // Connector endpoints return 401 when the connector token is invalid,
            // not when the user session is invalid
            const isConnectorEndpoint =
                error.config?.url?.includes('/connectors/')

            if (!isConnectorEndpoint) {
                clearAccessToken()
                // Don't redirect to login if we're on a share route
                if (!window.location.pathname.startsWith('/share/')) {
                    window.location.href = '/login'
                }
            }
        }
        return Promise.reject(error)
    }
)

export default axiosInstance
