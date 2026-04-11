import type { LucideIcon } from 'lucide-react'
import {
    Archive,
    Database,
    File,
    FileCode2,
    FileJson2,
    FileText,
    Folder,
    FolderOpen,
    Image,
    Settings2,
    Video
} from 'lucide-react'

type TreeVisualGroup =
    | 'folder'
    | 'code'
    | 'config'
    | 'docs'
    | 'data'
    | 'media'
    | 'archive'
    | 'default'

export interface TreeNodeVisual {
    Icon: LucideIcon
    label: string
    chipClassName: string
    containerClassName: string
    iconClassName: string
}

const VISUALS: Record<TreeVisualGroup, TreeNodeVisual> = {
    folder: {
        Icon: Folder,
        label: 'Folder',
        chipClassName:
            'border-firefly/20 bg-firefly/10 text-firefly dark:border-sky-blue/20 dark:bg-sky-blue/10 dark:text-sky-blue',
        containerClassName:
            'border-firefly/20 bg-firefly/10 dark:border-sky-blue/20 dark:bg-sky-blue/10',
        iconClassName: 'text-firefly dark:text-sky-blue'
    },
    code: {
        Icon: FileCode2,
        label: 'Code',
        chipClassName:
            'border-violet-500/20 bg-violet-500/10 text-violet-600 dark:border-violet-400/20 dark:bg-violet-400/10 dark:text-violet-300',
        containerClassName:
            'border-violet-500/20 bg-violet-500/10 dark:border-violet-400/20 dark:bg-violet-400/10',
        iconClassName: 'text-violet-600 dark:text-violet-300'
    },
    config: {
        Icon: Settings2,
        label: 'Config',
        chipClassName:
            'border-amber-500/20 bg-amber-500/10 text-amber-700 dark:border-amber-300/20 dark:bg-amber-300/10 dark:text-amber-200',
        containerClassName:
            'border-amber-500/20 bg-amber-500/10 dark:border-amber-300/20 dark:bg-amber-300/10',
        iconClassName: 'text-amber-700 dark:text-amber-200'
    },
    docs: {
        Icon: FileText,
        label: 'Docs',
        chipClassName:
            'border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:border-emerald-300/20 dark:bg-emerald-300/10 dark:text-emerald-200',
        containerClassName:
            'border-emerald-500/20 bg-emerald-500/10 dark:border-emerald-300/20 dark:bg-emerald-300/10',
        iconClassName: 'text-emerald-700 dark:text-emerald-200'
    },
    data: {
        Icon: Database,
        label: 'Data',
        chipClassName:
            'border-cyan-500/20 bg-cyan-500/10 text-cyan-700 dark:border-cyan-300/20 dark:bg-cyan-300/10 dark:text-cyan-200',
        containerClassName:
            'border-cyan-500/20 bg-cyan-500/10 dark:border-cyan-300/20 dark:bg-cyan-300/10',
        iconClassName: 'text-cyan-700 dark:text-cyan-200'
    },
    media: {
        Icon: Image,
        label: 'Media',
        chipClassName:
            'border-pink-500/20 bg-pink-500/10 text-pink-700 dark:border-pink-300/20 dark:bg-pink-300/10 dark:text-pink-200',
        containerClassName:
            'border-pink-500/20 bg-pink-500/10 dark:border-pink-300/20 dark:bg-pink-300/10',
        iconClassName: 'text-pink-700 dark:text-pink-200'
    },
    archive: {
        Icon: Archive,
        label: 'Archive',
        chipClassName:
            'border-slate-500/20 bg-slate-500/10 text-slate-700 dark:border-slate-300/20 dark:bg-slate-300/10 dark:text-slate-200',
        containerClassName:
            'border-slate-500/20 bg-slate-500/10 dark:border-slate-300/20 dark:bg-slate-300/10',
        iconClassName: 'text-slate-700 dark:text-slate-200'
    },
    default: {
        Icon: File,
        label: 'File',
        chipClassName:
            'border-neutral-300 bg-neutral-100 text-neutral-700 dark:border-white/15 dark:bg-white/5 dark:text-white/70',
        containerClassName:
            'border-neutral-300 bg-neutral-100 dark:border-white/15 dark:bg-white/5',
        iconClassName: 'text-neutral-700 dark:text-white/70'
    }
}

const extensionGroups: Record<TreeVisualGroup, string[]> = {
    folder: [],
    code: [
        'ts',
        'tsx',
        'js',
        'jsx',
        'py',
        'css',
        'scss',
        'html',
        'sh',
        'ps1'
    ],
    config: ['env', 'yaml', 'yml', 'ini', 'toml'],
    docs: ['md', 'mdx', 'txt'],
    data: ['json', 'sql', 'csv'],
    media: ['png', 'jpg', 'jpeg', 'svg', 'gif', 'mp4', 'webm'],
    archive: ['zip', 'tar', 'gz'],
    default: []
}

const getVisualGroup = (extension?: string): TreeVisualGroup => {
    const normalized = extension?.replace('.', '').toLowerCase()

    if (!normalized) return 'default'

    if (normalized === 'json') return 'data'
    if (normalized === 'mp4' || normalized === 'webm') return 'media'

    return (
        (Object.entries(extensionGroups).find(([, extensions]) =>
            extensions.includes(normalized)
        )?.[0] as TreeVisualGroup | undefined) ?? 'default'
    )
}

export const getTreeNodeVisual = ({
    kind,
    extension,
    expanded
}: {
    kind: 'folder' | 'file'
    extension?: string
    expanded?: boolean
}): TreeNodeVisual => {
    if (kind === 'folder') {
        return {
            ...VISUALS.folder,
            Icon: expanded ? FolderOpen : Folder
        }
    }

    const group = getVisualGroup(extension)
    const visual = VISUALS[group]

    if (group === 'media' && (extension === 'mp4' || extension === 'webm')) {
        return {
            ...visual,
            Icon: Video,
            label: 'Video'
        }
    }

    if (group === 'data' && extension === 'json') {
        return {
            ...visual,
            Icon: FileJson2,
            label: 'JSON'
        }
    }

    return visual
}

