import { AGENT_TYPE } from '@/typings'

export const INIT_TOOLS = [
    {
        name: 'Task Agent',
        nameKey: 'toolCatalog.init.taskAgent.name',
        description:
            'Enable task delegation to sub-agent for complex operations',
        descriptionKey: 'toolCatalog.init.taskAgent.description',
        icon: 'agent',
        isFill: false,
        isActive: false,
        isRequireKey: false
    },
    {
        name: 'Deep Research',
        nameKey: 'toolCatalog.init.deepResearch.name',
        description: 'Enable in-depth research capabilities',
        descriptionKey: 'toolCatalog.init.deepResearch.description',
        icon: 'search-status',
        isFill: true,
        isActive: false,
        isRequireKey: false
    },
    {
        name: 'Design Document',
        nameKey: 'toolCatalog.init.designDocument.name',
        description:
            'Design documents before developing for full-stack web development',
        descriptionKey: 'toolCatalog.init.designDocument.description',
        icon: 'note-2',
        isFill: false,
        isActive: false,
        isRequireKey: false
    },
    {
        name: 'Media Generation',
        nameKey: 'toolCatalog.init.mediaGeneration.name',
        description: 'Generate images and videos',
        descriptionKey: 'toolCatalog.init.mediaGeneration.description',
        icon: 'image',
        isFill: false,
        isActive: false,
        isRequireKey: false
    },
    {
        name: 'Codex',
        nameKey: 'toolCatalog.init.codex.name',
        description:
            'Enable OpenAI Codex for autonomous code generation and review',
        descriptionKey: 'toolCatalog.init.codex.description',
        icon: 'codex',
        isFill: false,
        isActive: false,
        isRequireKey: true
    },
    {
        name: 'Claude Code',
        nameKey: 'toolCatalog.init.claudeCode.name',
        description: 'Enable Claude Code for autonomous code generation',
        descriptionKey: 'toolCatalog.init.claudeCode.description',
        icon: 'claude',
        isFill: false,
        isActive: false,
        isRequireKey: true
    },
    {
        name: 'Agentic Memory',
        nameKey: 'toolCatalog.init.agenticMemory.name',
        description:
            'Enables the agent to update user memories during a run, only when real-time updates, explicit memory commands, or complex memory reasoning are required.',
        descriptionKey: 'toolCatalog.init.agenticMemory.description',
        icon: 'magic-pen',
        isFill: false,
        isActive: false,
        isRequireKey: false
    }
]

export const CHAT_TOOLS = [
    {
        name: 'Web Search',
        nameKey: 'toolCatalog.chatTools.webSearch.name',
        description: 'Search the web for information',
        descriptionKey: 'toolCatalog.chatTools.webSearch.description',
        icon: 'search-status',
        isFill: true,
        isActive: false,
        isRequireKey: false
    },
    {
        name: 'Web Visit',
        nameKey: 'toolCatalog.chatTools.webVisit.name',
        description: 'Visit and browse web pages',
        descriptionKey: 'toolCatalog.chatTools.webVisit.description',
        icon: 'browser',
        isFill: false,
        isActive: false,
        isRequireKey: false
    },
    {
        name: 'Image Search',
        nameKey: 'toolCatalog.chatTools.imageSearch.name',
        description: 'Search for images on the web',
        descriptionKey: 'toolCatalog.chatTools.imageSearch.description',
        icon: 'image',
        isFill: false,
        isActive: false,
        isRequireKey: false
    },
    {
        name: 'Code Interpreter',
        nameKey: 'toolCatalog.chatTools.codeInterpreter.name',
        description:
            'Execute code for calculations, data analysis, and visualizations',
        descriptionKey: 'toolCatalog.chatTools.codeInterpreter.description',
        icon: 'code',
        isFill: false,
        isActive: false,
        isRequireKey: false
    }
]

export const FEATURES = [
    {
        icon: 'monitor',
        name: 'Create a Website',
        nameKey: 'toolCatalog.features.createWebsite.name',
        type: AGENT_TYPE.WEBSITE_BUILD
    },
    {
        icon: 'mobile',
        name: 'Create a Mobile App',
        nameKey: 'toolCatalog.features.mobileApp.name',
        type: AGENT_TYPE.MOBILE_APP
    },
    {
        icon: 'presentation-2',
        name: 'Create Slide',
        nameKey: 'toolCatalog.features.createSlide.name',
        type: AGENT_TYPE.SLIDE
    },
    {
        icon: 'banana',
        name: 'AI Slide (Nano Banana)',
        nameKey: 'toolCatalog.features.aiSlideNanoBanana.name',
        type: AGENT_TYPE.SLIDE_NANO_BANANA
    },
    {
        icon: 'search-status',
        name: 'Deep Research',
        nameKey: 'toolCatalog.features.deepResearch.name',
        type: AGENT_TYPE.DEEP_RESEARCH
    },
    {
        icon: 'search-fast',
        name: 'Fast Research',
        nameKey: 'toolCatalog.features.fastResearch.name',
        type: AGENT_TYPE.FAST_RESEARCH
    },
    {
        icon: 'codex',
        name: 'Codex',
        nameKey: 'toolCatalog.features.codex.name',
        type: AGENT_TYPE.CODEX
    },
    {
        icon: 'claude',
        name: 'Claude Code',
        nameKey: 'toolCatalog.features.claudeCode.name',
        type: AGENT_TYPE.CLAUDE_CODE
    }
]

export const CHAT_FEATURES = [
    {
        name: 'Generate Image',
        nameKey: 'toolCatalog.chatFeatures.generateImage.name',
        icon: 'gallery-outline',
        type: 'image'
    },
    {
        name: 'Generate Infographic',
        nameKey: 'toolCatalog.chatFeatures.generateInfographic.name',
        icon: 'infographic-outline',
        type: 'infographic'
    },
    {
        name: 'Generate Poster',
        nameKey: 'toolCatalog.chatFeatures.generatePoster.name',
        icon: 'poster-outline',
        type: 'poster'
    },
    {
        name: 'Cook storybook',
        nameKey: 'toolCatalog.chatFeatures.cookStorybook.name',
        icon: 'book',
        type: 'storybook'
    },
    {
        icon: 'video-outline',
        name: 'Generate Video',
        nameKey: 'toolCatalog.chatFeatures.generateVideo.name',
        type: 'video' //AGENT_TYPE.MEDIA
    },
    {
        icon: 'brain',
        name: 'Model Council',
        nameKey: 'toolCatalog.chatFeatures.modelCouncil.name',
        type: 'council'
    }
]
