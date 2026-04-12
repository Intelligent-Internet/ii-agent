import Browser from '@/components/agent/browser'
import SearchBrowser from '@/components/agent/search-browser'
import CodeEditor from '@/components/code-editor'
import Terminal from '@/components/terminal'
import { TOOL, type ActionStep } from '@/typings/agent'
import { formatCoworkBuildHeaderLabel } from '../cowork-action-utils'
import type {
    CoworkBuildRendererDefinition,
    CoworkBuildRendererKey,
    CoworkBuildRendererContext
} from './cowork-build.types'

const escapeRegExp = (value: string) =>
    value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

const extractOutputJsonString = (raw?: string) => {
    if (!raw) {
        return undefined
    }

    const sectionKeys = ['output.json (merged)', 'output.json']

    for (const key of sectionKeys) {
        const matcher = new RegExp(
            `(?:^|\\n\\n)${escapeRegExp(key)}:\\n([\\s\\S]*?)(?=\\n\\n(?:output\\.json(?: \\(merged\\))?|stdout(?: \\(merged\\))?|stderr(?: \\(merged\\))?|output_files|error|chunk_summary):|$)`
        )
        const match = raw.match(matcher)
        const sectionBody = match?.[1]?.trim()

        if (!sectionBody) {
            continue
        }

        try {
            return JSON.stringify(JSON.parse(sectionBody), null, 2)
        } catch {
            return sectionBody
        }
    }

    return undefined
}

export const coworkBuildEventToolGroups = {
    terminal: new Set<TOOL>([
        TOOL.BASH,
        TOOL.BASH_INIT,
        TOOL.BASH_VIEW,
        TOOL.BASH_STOP,
        TOOL.BASH_KILL,
        TOOL.BASH_WRITE_TO_PROCESS,
        TOOL.LS,
        TOOL.GLOB,
        TOOL.GREP
    ]),
    code: new Set<TOOL>([
        TOOL.READ,
        TOOL.WRITE,
        TOOL.EDIT,
        TOOL.MULTI_EDIT,
        TOOL.APPLY_PATCH,
        TOOL.STR_REPLACE_BASED_EDIT
    ]),
    search: new Set<TOOL>([TOOL.WEB_SEARCH, TOOL.WEB_BATCH_SEARCH]),
    browser: new Set<TOOL>([
        TOOL.VISIT,
        TOOL.VISIT_COMPRESS,
        TOOL.BROWSER_USE,
        TOOL.BROWSER_CLICK,
        TOOL.BROWSER_CLOSE,
        TOOL.BROWSER_CONSOLE_MESSAGES,
        TOOL.BROWSER_DRAG,
        TOOL.BROWSER_EVALUATE,
        TOOL.BROWSER_HANDLE_DIALOG,
        TOOL.BROWSER_HOVER,
        TOOL.BROWSER_NAVIGATE,
        TOOL.BROWSER_NETWORK_REQUESTS,
        TOOL.BROWSER_PRESS_KEY,
        TOOL.BROWSER_SELECT_OPTION,
        TOOL.BROWSER_SNAPSHOT,
        TOOL.BROWSER_TAKE_SCREENSHOT,
        TOOL.BROWSER_TYPE,
        TOOL.BROWSER_WAIT_FOR,
        TOOL.BROWSER_TAB_CLOSE,
        TOOL.BROWSER_TAB_LIST,
        TOOL.BROWSER_TAB_NEW,
        TOOL.BROWSER_TAB_SELECT,
        TOOL.BROWSER_MOUSE_CLICK_XY,
        TOOL.BROWSER_MOUSE_DRAG_XY,
        TOOL.BROWSER_MOUSE_MOVE_XY,
        TOOL.BROWSER_NAVIGATION,
        TOOL.BROWSER_WAIT,
        TOOL.BROWSER_VIEW_INTERACTIVE_ELEMENTS,
        TOOL.BROWSER_SCROLL_DOWN,
        TOOL.BROWSER_SCROLL_UP,
        TOOL.BROWSER_SWITCH_TAB,
        TOOL.BROWSER_OPEN_NEW_TAB,
        TOOL.BROWSER_GET_SELECT_OPTIONS,
        TOOL.BROWSER_SELECT_DROPDOWN_OPTION,
        TOOL.BROWSER_RESTART,
        TOOL.BROWSER_ENTER_TEXT,
        TOOL.BROWSER_ENTER_MULTI_TEXTS
    ]),
    desktopTool: new Set<TOOL>([TOOL.WASM_RUN])
} satisfies Record<CoworkBuildRendererKey, Set<TOOL>>

const DesktopToolBuildCard = ({
    currentAction,
    currentToolCall
}: CoworkBuildRendererContext) => {
    const backendResult =
        currentToolCall?.result ??
        (typeof currentAction.data.result === 'string'
            ? currentAction.data.result
            : undefined)
    const outputJson = extractOutputJsonString(backendResult)

    return (
        <div className="h-full w-full overflow-auto px-3 py-4 md:px-4">
            <div className="mx-auto w-full max-w-[640px]">
                <pre className="whitespace-pre-wrap break-words rounded-2xl bg-white/70 px-4 py-3 text-xs text-black/75 dark:bg-white/[0.08] dark:text-white/75">
                    {outputJson ??
                        backendResult ??
                        `${formatCoworkBuildHeaderLabel(currentAction) || 'Process'} is still running...`}
                </pre>
            </div>
        </div>
    )
}

export const coworkBuildRendererCatalog: Record<
    CoworkBuildRendererKey,
    CoworkBuildRendererDefinition
> = {
    terminal: {
        key: 'terminal',
        matches: (action: ActionStep) =>
            coworkBuildEventToolGroups.terminal.has(action.type),
        render: ({ currentAction }: CoworkBuildRendererContext) => (
            <Terminal
                className="w-full h-full !p-0"
                currentActionData={currentAction}
            />
        )
    },
    code: {
        key: 'code',
        matches: (action: ActionStep) =>
            coworkBuildEventToolGroups.code.has(action.type),
        render: ({
            currentAction,
            previewContent,
            previewPath
        }: CoworkBuildRendererContext) => (
            <CodeEditor
                className="w-full h-full"
                currentActionData={currentAction}
                activeFile={previewPath ?? 'preview.txt'}
                filesContent={{
                    [previewPath ?? 'preview.txt']: previewContent
                }}
                showEditorOnly
            />
        )
    },
    search: {
        key: 'search',
        matches: (action: ActionStep) =>
            coworkBuildEventToolGroups.search.has(action.type),
        render: ({
            searchKeyword,
            searchResults
        }: CoworkBuildRendererContext) => (
            <SearchBrowser
                className="h-full"
                keyword={searchKeyword}
                search_results={searchResults}
            />
        )
    },
    browser: {
        key: 'browser',
        matches: (action: ActionStep) =>
            coworkBuildEventToolGroups.browser.has(action.type),
        render: ({ browserUrl, browserRaw }: CoworkBuildRendererContext) => (
            <Browser
                isHideHeader
                className="!h-full !overflow-auto !rounded-none"
                contentClassName="bg-grey dark:bg-black h-full"
                markdownClassName="overflow-visible h-full"
                url={browserUrl}
                raw={browserRaw}
            />
        )
    },
    desktopTool: {
        key: 'desktopTool',
        matches: (action: ActionStep) =>
            coworkBuildEventToolGroups.desktopTool.has(action.type),
        render: (context: CoworkBuildRendererContext) => (
            <DesktopToolBuildCard {...context} />
        )
    }
}

export const pickCoworkBuildRenderers = (
    ...keys: CoworkBuildRendererKey[]
): CoworkBuildRendererDefinition[] =>
    keys.map((key) => coworkBuildRendererCatalog[key])
