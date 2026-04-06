export const COWORK_HOME_LABEL = 'Homepage'

export const COWORK_MODES = [
    {
        id: 'organize-file-folder',
        label: 'Organize file/folder'
    }
] as const

export type CoworkModeId = (typeof COWORK_MODES)[number]['id']

export const getCoworkModeLabel = (mode: CoworkModeId | null) =>
    COWORK_MODES.find((item) => item.id === mode)?.label ?? COWORK_HOME_LABEL
