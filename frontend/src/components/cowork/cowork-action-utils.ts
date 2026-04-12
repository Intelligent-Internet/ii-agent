import { TOOL, type ActionStep } from '@/typings/agent'

export const readCoworkRecord = (
    value: unknown
): Record<string, unknown> | undefined => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
        return undefined
    }

    return value as Record<string, unknown>
}

export const readCoworkString = (
    record: Record<string, unknown>,
    key: string
) => {
    const value = record[key]
    return typeof value === 'string' && value.trim() ? value.trim() : undefined
}

const lastPathSegment = (value?: string) => {
    if (!value) {
        return undefined
    }

    const parts = value.split(/[\\/]/).filter(Boolean)
    return parts.at(-1)
}

export const getCoworkSkillName = (
    toolInput: unknown
) => {
    const input = readCoworkRecord(toolInput)

    if (!input) {
        return undefined
    }

    return (
        readCoworkString(input, 'skill_name') ??
        readCoworkString(input, 'skill')
    )
}

export const getCoworkWasmPrimaryInputFileName = (
    toolInput: unknown
) => {
    const input = readCoworkRecord(toolInput)

    if (!input) {
        return undefined
    }

    if (Array.isArray(input.input_files)) {
        for (const entry of input.input_files) {
            const file = readCoworkRecord(entry)
            if (!file) {
                continue
            }

            const fileName =
                lastPathSegment(readCoworkString(file, 'path')) ??
                readCoworkString(file, 'name')

            if (fileName) {
                return fileName
            }
        }
    }

    return (
        lastPathSegment(readCoworkString(input, 'file_path')) ??
        lastPathSegment(readCoworkString(input, 'path')) ??
        lastPathSegment(readCoworkString(input, 'file')) ??
        lastPathSegment(readCoworkString(input, 'filename'))
    )
}

export const getCoworkWasmModuleName = (
    toolInput: unknown
) => {
    const input = readCoworkRecord(toolInput)
    return input ? readCoworkString(input, 'module') : undefined
}

export const getCoworkActionValue = (action?: ActionStep) => {
    if (!action) {
        return undefined
    }

    switch (action.type) {
        case TOOL.DESKTOP_SKILL_RUN:
            return getCoworkSkillName(action.data.tool_input)
        case TOOL.WASM_RUN:
            return (
                getCoworkWasmPrimaryInputFileName(action.data.tool_input) ??
                getCoworkWasmModuleName(action.data.tool_input)
            )
        default:
            return undefined
    }
}

export const formatCoworkBuildHeaderLabel = (action?: ActionStep) => {
    if (!action) {
        return undefined
    }

    if (action.type === TOOL.DESKTOP_SKILL_RUN) {
        const skillName = getCoworkSkillName(action.data.tool_input)
        return skillName ? `Desktop Skill: ${skillName}` : 'Desktop Skill'
    }

    if (action.type === TOOL.WASM_RUN) {
        const fileName = getCoworkWasmPrimaryInputFileName(
            action.data.tool_input
        )
        if (fileName) {
            return `Process ${fileName}`
        }

        const moduleName = getCoworkWasmModuleName(action.data.tool_input)
        return moduleName ? `Process ${moduleName}` : 'Process'
    }

    return action.data.tool_display_name || action.data.tool_name
}

export const inferCoworkToolDisplayName = ({
    toolName,
    displayName,
    toolInput
}: {
    toolName?: string
    displayName?: string
    toolInput?: unknown
}) => {
    const normalizedToolName = toolName?.trim().toLowerCase()
    const skillName = getCoworkSkillName(toolInput)

    switch (normalizedToolName) {
        case TOOL.DESKTOP_SKILL_RUN:
            return 'Desktop Skill'
        case TOOL.WASM_RUN:
            return 'Process'
        case TOOL.SKILL.toLowerCase():
            return skillName ? `Skill: ${skillName}` : 'Skill'
        default:
            return displayName?.trim() || toolName?.trim() || 'Tool'
    }
}

export const normalizeCoworkToolNameForUi = (toolName?: string) => {
    const normalized = toolName?.trim()
    if (!normalized) {
        return undefined
    }

    switch (normalized.toLowerCase()) {
        case 'ls':
            return TOOL.LS
        case 'bash':
            return TOOL.BASH
        case 'bashinit':
        case 'bash_init':
            return TOOL.BASH_INIT
        case 'bashview':
        case 'bash_view':
            return TOOL.BASH_VIEW
        case 'bashstop':
        case 'bash_stop':
            return TOOL.BASH_STOP
        case 'bashkill':
        case 'bash_kill':
            return TOOL.BASH_KILL
        case 'bashlist':
        case 'bash_list':
            return TOOL.BASH_LIST
        case 'bashwritetoprocess':
        case 'bash_write_to_process':
            return TOOL.BASH_WRITE_TO_PROCESS
        case 'read':
        case 'read_file':
            return TOOL.READ
        case 'write':
        case 'write_file':
            return TOOL.WRITE
        case 'edit':
        case 'edit_file':
            return TOOL.EDIT
        case 'apply_patch':
            return TOOL.APPLY_PATCH
        case 'todowrite':
        case 'todo_write':
            return TOOL.TODO_WRITE
        case 'glob':
            return TOOL.GLOB
        case 'grep':
        case 'astgrep':
            return TOOL.GREP
        case 'desktop_skill_run':
            return TOOL.DESKTOP_SKILL_RUN
        case 'wasm_run':
            return TOOL.WASM_RUN
        case 'multiedit':
        case 'multi_edit':
            return TOOL.MULTI_EDIT
        case 'list_dir':
            return TOOL.LS
        default:
            return normalized
    }
}

export const isCoworkBuildPanelActionVisible = (action?: ActionStep | null) =>
    Boolean(action && action.type !== TOOL.DESKTOP_SKILL_RUN)
