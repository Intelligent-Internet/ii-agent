import { IMCPTool } from '@/typings/agent'

export const MCP_TOOLS: IMCPTool[] = [
    {
        name: 'Algolia',
        author: 'algolia',
        description:
            'Use AI agents to provision, configure, and query your Algolia search indices.',
        logo: 'https://www.algolia.com/favicon.ico',
        url: 'https://github.com/algolia/mcp',
        config: {
            mcpServers: {
                algolia: {
                    command: '/path/to/the/repo/cmd/mcp/mcp',
                    env: {
                        ALGOLIA_APP_ID: '<APP_ID>',
                        ALGOLIA_INDEX_NAME: '<INDEX_NAME>',
                        ALGOLIA_API_KEY: '<API_KEY>',
                        ALGOLIA_WRITE_API_KEY: '<ADMIN_API_KEY>',
                        MCP_ENABLED_TOOLS: '',
                        MCP_SERVER_TYPE: 'stdio',
                        MCP_SSE_PORT: '8080'
                    }
                }
            }
        },
        isRequireKey: true
    },
    {
        name: 'Auth0',
        author: 'auth0',
        description:
            'MCP server for interacting with your Auth0 tenant, supporting creating and modifying actions, applications, forms, logs, resource servers, and more.',
        logo: 'https://seeklogo.com/images/A/auth0-logo-CB96B17A7D-seeklogo.com.png',
        url: 'https://github.com/auth0/auth0-mcp-server',
        config: {
            mcpServers: {
                auth0: {
                    command: 'npx',
                    args: ['-y', '@auth0/auth0-mcp-server', 'run'],
                    capabilities: ['tools'],
                    env: {
                        DEBUG: 'auth0-mcp'
                    }
                }
            }
        }
    },
    {
        name: 'Canva',
        author: 'canva',
        description:
            'Provide AI - powered development assistance for Canva apps and integrations.',
        logo: 'https://canva.com/favicon.ico',
        url: 'https://www.canva.dev/docs/apps/mcp-server/',
        config: {
            mcpServers: {
                'canva-dev': {
                    command: 'npx',
                    args: ['-y', '@canva/cli@latest', 'mcp']
                }
            }
        }
    },
    {
        name: 'Cloudflare',
        author: 'cloudflare',
        description:
            'Deploy, configure & interrogate your resources on the Cloudflare developer platform (e.g. Workers/KV/R2/D1)',
        logo: 'https://www.cloudflare.com/favicon.ico',
        url: 'https://github.com/cloudflare/mcp-server-cloudflare',
        config: {
            mcpServers: {
                'cloudflare-observability': {
                    command: 'npx',
                    args: [
                        'mcp-remote',
                        'https://observability.mcp.cloudflare.com/sse'
                    ]
                },
                'cloudflare-bindings': {
                    command: 'npx',
                    args: [
                        'mcp-remote',
                        'https://bindings.mcp.cloudflare.com/sse'
                    ]
                }
            }
        }
    },
    {
        name: 'Firebase',
        author: 'firebase',
        description: `Firebase's experimental MCP Server to power your AI Tools`,
        logo: 'https://firebase.google.com/favicon.ico',
        url: 'https://github.com/firebase/firebase-tools/tree/master/src/mcp',
        config: {
            mcpServers: {
                firebase: {
                    command: 'npx',
                    args: [
                        '-y',
                        'firebase-tools',
                        'experimental:mcp',
                        '--dir',
                        '.'
                    ]
                }
            }
        }
    },
    {
        name: 'Hugging Face',
        author: 'huggingface',
        description:
            'Connect to the Hugging Face Hub APIs programmatically: semantic search for spaces and papers, exploration of datasets and models, and access to all compatible MCP Gradio tool spaces!',
        logo: 'https://huggingface.co/favicon.ico',
        url: 'https://huggingface.co/settings/mcp',
        config: {
            servers: {
                'hf-mcp-server': {
                    url: 'https://huggingface.co/mcp',
                    headers: {
                        Authorization: 'Bearer <YOUR_HF_TOKEN>'
                    }
                }
            }
        }
    },
    {
        name: 'Parallel Search',
        author: 'parallel',
        description:
            'Free web search in Fast mode and page fetching, with no account or API key required. Anonymous usage is rate limited.',
        logo: 'https://parallel.ai/favicon.ico',
        url: 'https://docs.parallel.ai/integrations/mcp/search-mcp',
        config: {
            mcpServers: {
                'parallel-search': {
                    url: 'https://search.parallel.ai/mcp',
                    headers: {
                        'User-Agent':
                            'ii-agent/0.1.0 (https://github.com/Intelligent-Internet/ii-agent)'
                    }
                }
            }
        },
        isRequireKey: false
    }
]
