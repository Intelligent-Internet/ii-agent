import type {
    ImageAspectRatio,
    ImageResolution,
    VideoDuration,
    VideoResolution,
    VideoAspectRatio
} from '@/typings/agent'
import type { ChatMediaType } from './media-type-config'

export type ChatMediaModel = {
    id: string
    label: string
    model_name: string
    provider: 'gemini' | 'vertex' | 'black-forest' | 'openai' | 'custom'
    type: ChatMediaType
    description: string
    default_prompt?: string
    source?: 'user' | 'system'
    // Image-specific properties
    supported_resolutions?: ImageResolution[]
    supported_aspect_ratios?: ImageAspectRatio[]
    // Video-specific properties
    supported_durations?: VideoDuration[]
    supported_video_resolutions?: VideoResolution[]
    supported_video_aspect_ratios?: VideoAspectRatio[]
    supports_audio?: boolean
    supports_multishot?: boolean
    supports_start_frame?: boolean
    supports_end_frame?: boolean
    icon: string
}

// Re-export media service for fetching models from API
export { mediaService } from '@/services/media.service'
export type {
    VideoModelsResponse,
    ImageModelsResponse,
    MediaModelsResponse
} from '@/services/media.service'

// Static models kept for backwards compatibility with existing code
// New code should use useMediaModels() hook or mediaService to fetch from API

export const CHAT_IMAGE_MODELS: ChatMediaModel[] = [
    {
        id: 'nano-banana-pro',
        label: 'media.models.nanoBananaPro.label',
        model_name: 'gemini-3-pro-image-preview',
        provider: 'gemini',
        type: 'image',
        description: 'media.models.nanoBananaPro.description',
        // Gemini 3 Pro: 1K, 2K, 4K and aspect ratios 1:1, 2:3, 3:2, 3:4, 4:3, 9:16, 16:9, 21:9
        supported_resolutions: ['1K', '2K', '4K'],
        supported_aspect_ratios: [
            '1:1',
            '2:3',
            '3:2',
            '3:4',
            '4:3',
            '9:16',
            '16:9',
            '21:9'
        ],
        icon: 'nano-banana'
    },
    {
        id: 'gpt-image-1.5',
        label: 'media.models.gptImage15.label',
        model_name: 'gpt-image-2.6-sunburst',
        provider: 'openai',
        type: 'image',
        description: 'media.models.gptImage15.description',
        // GPT Image 1.5 only supports: 1024x1024 (1:1), 1536x1024 (3:2 landscape), 1024x1536 (2:3 portrait)
        // No resolution options - fixed at these sizes
        supported_resolutions: ['1K'],
        supported_aspect_ratios: ['1:1', '3:2', '2:3'],
        icon: 'openai'
    },
    {
        id: 'imagen-4.0-generate-001',
        label: 'media.models.imagen40Generate001.label',
        model_name: 'imagen-4.0-generate-001',
        provider: 'gemini',
        type: 'image',
        description: 'media.models.imagen40Generate001.description',
        supported_resolutions: ['1K', '2K'],
        supported_aspect_ratios: [
            '1:1',
            '2:3',
            '3:2',
            '3:4',
            '4:3',
            '9:16',
            '16:9'
        ],
        icon: 'google'
    }
]

export const CHAT_STORYBOOK_MODELS: ChatMediaModel[] = [
    {
        id: 'nano-banana-pro',
        label: 'media.models.nanoBananaPro.label',
        model_name: 'gemini-3-pro-image-preview',
        provider: 'gemini',
        type: 'storybook',
        description: 'media.models.nanoBananaPro.description',
        // Gemini 3 Pro: 1K, 2K, 4K and aspect ratios 1:1, 2:3, 3:2, 3:4, 4:3, 9:16, 16:9, 21:9
        supported_resolutions: ['1K', '2K', '4K'],
        supported_aspect_ratios: [
            '1:1',
            '2:3',
            '3:2',
            '3:4',
            '4:3',
            '9:16',
            '16:9'
        ],
        icon: 'nano-banana'
    },
    {
        id: 'gpt-image-1.5',
        label: 'media.models.gptImage15.label',
        model_name: 'gpt-image-1.5',
        provider: 'openai',
        type: 'storybook',
        description: 'media.models.gptImage15.description',
        supported_resolutions: ['1K'],
        supported_aspect_ratios: ['1:1', '2:3', '3:2'],
        icon: 'openai'
    },
    {
        id: 'imagen-4.0-generate-001',
        label: 'media.models.imagen40Generate001.label',
        model_name: 'imagen-4.0-generate-001',
        provider: 'gemini',
        type: 'storybook',
        description: 'media.models.imagen40Generate001.description',
        supported_resolutions: ['1K', '2K'],
        supported_aspect_ratios: ['1:1', '2:3', '3:4', '4:3', '16:9'],
        icon: 'google'
    }
]

// NOTE: Temporarily only Veo 3.1 is enabled for chat mode video generation
export const CHAT_VIDEO_MODELS: ChatMediaModel[] = [
    {
        id: 'veo-3.1-premium',
        label: 'media.models.veo31Premium.label',
        model_name: 'veo-3.1-premium',
        provider: 'vertex',
        type: 'video',
        description: 'media.models.veo31Premium.description',
        supported_durations: ['4s', '6s', '8s', '10s', '12s', '18s', '24s', '30s'],
        supported_video_resolutions: ['720p', '1080p'],
        supported_video_aspect_ratios: ['16:9', '9:16'],
        supports_audio: true,
        supports_multishot: true,
        supports_start_frame: true,
        supports_end_frame: true,
        icon: 'google'
    }
]

export const CHAT_MEDIA_SUGGESTIONS: Record<ChatMediaType, string> = {
    image: 'media.suggestions.image',
    infographic: 'media.suggestions.infographic',
    poster: 'media.suggestions.poster',
    storybook: 'media.suggestions.storybook',
    video: 'media.suggestions.video'
}
