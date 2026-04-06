export interface ChannelField {
    key: string
    type: 'secret' | 'text' | 'number' | 'list' | 'boolean'
    required: boolean
    placeholder: string
    advanced: boolean
}

export interface ChannelDef {
    name: string
    icon: string
    fields: ChannelField[]
}

export const CHANNEL_DEFS: ChannelDef[] = [
    {
        name: 'telegram',
        icon: 'https://logos.composio.dev/api/telegram',
        fields: [
            { key: 'bot_token_env', type: 'secret', required: true, placeholder: '123456:ABC-DEF...', advanced: false },
            { key: 'allowed_users', type: 'list', required: false, placeholder: '12345, 67890', advanced: true },
            // { key: 'default_agent', type: 'text', required: false, placeholder: 'assistant', advanced: true },
            { key: 'poll_interval_secs', type: 'number', required: false, placeholder: '1', advanced: true }
        ]
    },
    {
        name: 'discord',
        icon: 'https://logos.composio.dev/api/discord',
        fields: [
            { key: 'bot_token_env', type: 'secret', required: true, placeholder: 'MTIz...', advanced: false },
            { key: 'allowed_guilds', type: 'list', required: false, placeholder: '123456789, 987654321', advanced: true },
            { key: 'allowed_users', type: 'list', required: false, placeholder: '123456789, 987654321', advanced: true },
            // { key: 'default_agent', type: 'text', required: false, placeholder: 'assistant', advanced: true },
            { key: 'intents', type: 'number', required: false, placeholder: '37376', advanced: true },
            // { key: 'ignore_bots', type: 'boolean', required: false, placeholder: 'true', advanced: true }
        ]
    },
    {
        name: 'slack',
        icon: 'https://logos.composio.dev/api/slack',
        fields: [
            { key: 'app_token_env', type: 'secret', required: true, placeholder: 'xapp-1-...', advanced: false },
            { key: 'bot_token_env', type: 'secret', required: true, placeholder: 'xoxb-...', advanced: false },
            { key: 'allowed_channels', type: 'list', required: false, placeholder: 'C01234, C56789', advanced: true },
            // { key: 'default_agent', type: 'text', required: false, placeholder: 'assistant', advanced: true }
        ]
    }
]
