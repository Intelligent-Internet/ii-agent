import Browser from '@/components/agent/browser'
import SearchBrowser from '@/components/agent/search-browser'
import CodeEditor from '@/components/code-editor'
import Terminal from '@/components/terminal'
import { TOOL, type ActionStep } from '@/typings/agent'
import type {
    CoworkBuildRendererDefinition,
    CoworkBuildRendererKey,
    CoworkBuildRendererContext
} from './cowork-build.types'

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
    ])
} satisfies Record<CoworkBuildRendererKey, Set<TOOL>>

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
        render: ({
            browserUrl,
            browserRaw
        }: CoworkBuildRendererContext) => (
            <Browser
                isHideHeader
                className="!h-full !overflow-auto !rounded-none"
                contentClassName="bg-grey dark:bg-black h-full"
                markdownClassName="overflow-visible h-full"
                url={browserUrl}
                raw={browserRaw}
            />
        )
    }
}

export const pickCoworkBuildRenderers = (
    ...keys: CoworkBuildRendererKey[]
): CoworkBuildRendererDefinition[] =>
    keys.map((key) => coworkBuildRendererCatalog[key])
