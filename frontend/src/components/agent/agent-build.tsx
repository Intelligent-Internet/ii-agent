import { useMemo } from 'react'
import first from 'lodash/first'
import last from 'lodash/last'

import isEmpty from 'lodash/isEmpty'
import { selectCurrentActionData, useAppSelector } from '@/state'
import { Icon } from '../ui/icon'
import CodeEditor from '../code-editor'
import { TOOL, FileURLContent } from '@/typings/agent'
import Terminal from '../terminal'
import { extractUrls, identifyFilesNeeded, parseJson } from '@/lib/utils'
import Browser from './browser'
import DiffCodeEditor from '../diff-editor'
import SearchBrowser from './search-browser'
import AgentController from './agent-controller'
import { Button } from '../ui/button'
import { useIsMobile } from '@/hooks/use-mobile'
import { useWindowSize } from '@/hooks/use-window-size'

interface AgentBuildProps {
    className?: string
}

const AgentBuild = ({ className }: AgentBuildProps) => {
    const currentActionData = useAppSelector(selectCurrentActionData)
    const isMobile = useIsMobile()
    const windowWidth = useWindowSize()

    const tab = useMemo(() => {
        // deploy
        if (
            currentActionData?.type &&
            [TOOL.REGISTER_DEPLOYMENT].includes(currentActionData?.type)
        )
            return 'deploy'

        // browser
        if (
            currentActionData?.type &&
            [
                TOOL.VISIT,
                TOOL.VISIT_COMPRESS,
                TOOL.IMAGE_GENERATE,
                TOOL.READ_REMOTE_IMAGE,
                TOOL.VIDEO_GENERATE,
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
            ].includes(currentActionData?.type)
        )
            return 'browser'

        // image_browser
        if (
            currentActionData?.type &&
            [TOOL.IMAGE_SEARCH].includes(currentActionData?.type)
        )
            return 'image_browser'

        // search_browser
        if (
            currentActionData?.type &&
            [TOOL.WEB_SEARCH, TOOL.WEB_BATCH_SEARCH].includes(
                currentActionData?.type
            )
        )
            return 'search_browser'

        // terminal
        if (
            currentActionData?.type &&
            [
                TOOL.BASH,
                TOOL.BASH_INIT,
                TOOL.BASH_KILL,
                TOOL.BASH_VIEW,
                TOOL.BASH_STOP,
                TOOL.BASH_WRITE_TO_PROCESS,
                TOOL.LS,
                TOOL.GLOB,
                TOOL.GREP
            ].includes(currentActionData?.type)
        )
            return 'terminal'

        // slide
        if (
            currentActionData?.type &&
            [
                TOOL.SLIDE_WRITE,
                TOOL.SLIDE_EDIT,
                TOOL.SLIDE_APPLY_PATCH
            ].includes(currentActionData?.type)
        )
            return 'slide'

        // code
        return 'code'
    }, [currentActionData?.type])

    const fileName = useMemo(() => {
        if (currentActionData?.data?.tool_name === TOOL.APPLY_PATCH) {
            if (!isEmpty(currentActionData?.data?.tool_input?.changes)) {
                return first(
                    Object.keys(
                        currentActionData?.data?.tool_input?.changes
                    ).map((file) => last(file.split('/')))
                )
            }
            return last(
                first(
                    identifyFilesNeeded(
                        currentActionData?.data.tool_input?.input || ''
                    )
                )?.split('/')
            )
        }
        const path =
            currentActionData?.data?.tool_input?.path ||
            currentActionData?.data?.tool_input?.file_path

        if (!path) return undefined

        return path
    }, [
        currentActionData?.data?.tool_input?.path,
        currentActionData?.data?.tool_input?.file_path,
        currentActionData?.data?.tool_name
    ])

    const fileContent = useMemo(() => {
        if (currentActionData?.data?.tool_name === TOOL.WRITE) {
            return currentActionData?.data?.tool_input?.content as string
        } else if (
            currentActionData?.data?.tool_name === TOOL.EDIT ||
            currentActionData?.data?.tool_name === TOOL.MULTI_EDIT
        ) {
            return currentActionData?.data?.tool_input?.new_string as string
        } else if (currentActionData?.data?.tool_name === TOOL.APPLY_PATCH) {
            if (!isEmpty(currentActionData?.data?.tool_input?.changes)) {
                const changes = currentActionData?.data?.tool_input?.changes
                const change = changes[Object.keys(changes)[0]]
                if (change?.add || change?.delete) {
                    return change?.add?.content || change?.delete?.content
                }
                return change?.update?.unified_diff as string
            }
            return (
                currentActionData?.data?.result as { new_content: string }[]
            )?.[0]?.new_content as string
        } else if (
            currentActionData?.data?.tool_name === TOOL.STR_REPLACE_BASED_EDIT
        ) {
            if (
                currentActionData?.data?.tool_input?.command?.startsWith('view')
            ) {
                return currentActionData?.data?.result as string
            } else if (
                currentActionData?.data?.tool_input?.command?.startsWith(
                    'create'
                )
            ) {
                return currentActionData?.data?.tool_input?.file_text as string
            }
            return ''
        }

        return currentActionData?.data?.result as string
    }, [
        currentActionData?.data?.tool_input?.content,
        currentActionData?.data?.result,
        currentActionData?.data?.tool_input?.new_string,
        currentActionData?.data?.tool_input?.command,
        currentActionData?.data?.tool_input?.file_text
    ])

    const isViewTool = useMemo(() => {
        if (
            currentActionData?.data?.tool_name === TOOL.APPLY_PATCH &&
            !isEmpty(currentActionData?.data?.tool_input?.changes)
        )
            return true

        if (
            [TOOL.EDIT, TOOL.MULTI_EDIT].includes(
                currentActionData?.data?.tool_name as TOOL
            )
        )
            return false

        return currentActionData?.data?.tool_name ===
            TOOL.STR_REPLACE_BASED_EDIT
            ? currentActionData?.data?.tool_input?.command?.startsWith(
                  'view'
              ) ||
                  currentActionData?.data?.tool_input?.command?.startsWith(
                      'create'
                  )
            : true
    }, [
        currentActionData?.data?.tool_name,
        currentActionData?.data?.tool_input?.command
    ])

    const isEditTool = useMemo(() => {
        if (
            currentActionData?.data?.tool_name === TOOL.APPLY_PATCH &&
            isEmpty(currentActionData?.data?.tool_input?.changes)
        ) {
            return true
        }
        if (
            [TOOL.EDIT, TOOL.MULTI_EDIT].includes(
                currentActionData?.data?.tool_name as TOOL
            )
        )
            return true

        return (
            currentActionData?.data?.tool_name ===
                TOOL.STR_REPLACE_BASED_EDIT &&
            !currentActionData?.data?.tool_input?.command?.startsWith('view') &&
            !currentActionData?.data?.tool_input?.command?.startsWith('create')
        )
    }, [
        currentActionData?.data?.tool_name,
        currentActionData?.data?.tool_input?.command
    ])

    const searchImages = useMemo(() => {
        if (currentActionData?.type !== TOOL.IMAGE_SEARCH) return []
        return parseJson(currentActionData?.data?.result as string) as {
            image_url: string
        }[]
    }, [currentActionData?.type, currentActionData?.data?.result])

    const buildingTitle = useMemo(() => {
        if (currentActionData?.type === TOOL.IMAGE_SEARCH) return 'Searching'
        if (currentActionData?.type === TOOL.IMAGE_GENERATE)
            return 'Generating Image'
        if (currentActionData?.type === TOOL.READ_REMOTE_IMAGE)
            return 'Reading Remote Image'
        if (currentActionData?.type === TOOL.VIDEO_GENERATE)
            return 'Generating Video'

        if (
            currentActionData?.type === TOOL.WEB_SEARCH ||
            currentActionData?.type === TOOL.WEB_BATCH_SEARCH
        ) {
            const toolInput = currentActionData?.data?.tool_input
            const searchTerm =
                toolInput?.query ||
                (toolInput?.queries ? toolInput.queries.join(', ') : '')
            return `Searching: "${searchTerm}"`
        }

        if (
            currentActionData?.type === TOOL.VISIT ||
            currentActionData?.type === TOOL.VISIT_COMPRESS
        )
            return 'Crawling'
        if (currentActionData?.type === TOOL.BROWSER_USE) return 'Browsing'

        // Handle all new browser tools
        if (currentActionData?.type === TOOL.BROWSER_CLICK) return 'Clicking'
        if (currentActionData?.type === TOOL.BROWSER_CLOSE)
            return 'Closing Browser'
        if (currentActionData?.type === TOOL.BROWSER_CONSOLE_MESSAGES)
            return 'Getting Console Messages'
        if (currentActionData?.type === TOOL.BROWSER_DRAG) return 'Dragging'
        if (currentActionData?.type === TOOL.BROWSER_EVALUATE)
            return 'Evaluating JavaScript'
        if (currentActionData?.type === TOOL.BROWSER_HANDLE_DIALOG)
            return 'Handling Dialog'
        if (currentActionData?.type === TOOL.BROWSER_HOVER) return 'Hovering'
        if (currentActionData?.type === TOOL.BROWSER_NAVIGATE)
            return 'Navigating'
        if (currentActionData?.type === TOOL.BROWSER_NETWORK_REQUESTS)
            return 'Getting Network Requests'
        if (currentActionData?.type === TOOL.BROWSER_PRESS_KEY)
            return 'Pressing Key'
        if (currentActionData?.type === TOOL.BROWSER_SELECT_OPTION)
            return 'Selecting Option'
        if (currentActionData?.type === TOOL.BROWSER_SNAPSHOT)
            return 'Taking Snapshot'
        if (currentActionData?.type === TOOL.BROWSER_TAKE_SCREENSHOT)
            return 'Taking Screenshot'
        if (currentActionData?.type === TOOL.BROWSER_TYPE) return 'Typing'
        if (currentActionData?.type === TOOL.BROWSER_WAIT_FOR) return 'Waiting'
        if (currentActionData?.type === TOOL.BROWSER_TAB_CLOSE)
            return 'Closing Tab'
        if (currentActionData?.type === TOOL.BROWSER_TAB_LIST)
            return 'Listing Tabs'
        if (currentActionData?.type === TOOL.BROWSER_TAB_NEW)
            return 'Opening New Tab'
        if (currentActionData?.type === TOOL.BROWSER_TAB_SELECT)
            return 'Selecting Tab'
        if (currentActionData?.type === TOOL.BROWSER_MOUSE_CLICK_XY)
            return 'Clicking at Position'
        if (currentActionData?.type === TOOL.BROWSER_MOUSE_DRAG_XY)
            return 'Dragging at Position'
        if (currentActionData?.type === TOOL.BROWSER_MOUSE_MOVE_XY)
            return 'Moving Mouse'
        if (currentActionData?.type === TOOL.BROWSER_NAVIGATION)
            return 'Browser Navigation'
        if (currentActionData?.type === TOOL.BROWSER_WAIT) return 'Waiting'
        if (currentActionData?.type === TOOL.BROWSER_VIEW_INTERACTIVE_ELEMENTS)
            return 'Viewing Interactive Elements'
        if (currentActionData?.type === TOOL.BROWSER_SCROLL_DOWN)
            return 'Scrolling Down'
        if (currentActionData?.type === TOOL.BROWSER_SCROLL_UP)
            return 'Scrolling Up'
        if (currentActionData?.type === TOOL.BROWSER_SWITCH_TAB)
            return 'Switching Tab'
        if (currentActionData?.type === TOOL.BROWSER_OPEN_NEW_TAB)
            return 'Opening New Tab'
        if (currentActionData?.type === TOOL.BROWSER_GET_SELECT_OPTIONS)
            return 'Getting Select Options'
        if (currentActionData?.type === TOOL.BROWSER_SELECT_DROPDOWN_OPTION)
            return 'Selecting Dropdown Option'
        if (currentActionData?.type === TOOL.BROWSER_RESTART)
            return 'Restarting Browser'
        if (currentActionData?.type === TOOL.BROWSER_ENTER_TEXT)
            return 'Entering Text'
        if (currentActionData?.type === TOOL.BROWSER_ENTER_MULTI_TEXTS)
            return 'Entering Multiple Texts'
        if (currentActionData?.type === TOOL.READ) return 'Reading'
        if (currentActionData?.type === TOOL.REGISTER_DEPLOYMENT)
            return 'Deploying'

        return 'Generating'
    }, [currentActionData])

    const getBrowserFileName = useMemo(() => {
        const type = currentActionData?.type
        const value = currentActionData?.data

        let browserValue = ''

        switch (type) {
            case TOOL.BROWSER_CLICK:
                browserValue = value?.tool_input?.element || ''
                break
            case TOOL.BROWSER_TAKE_SCREENSHOT:
                browserValue = value?.tool_input?.filename || ''
                break
            case TOOL.BROWSER_TYPE:
                browserValue = value?.tool_input?.text || ''
                break
            case TOOL.BROWSER_PRESS_KEY:
                browserValue = value?.tool_input?.key || ''
                break
            case TOOL.BROWSER_MOUSE_CLICK_XY:
            case TOOL.BROWSER_MOUSE_DRAG_XY:
            case TOOL.BROWSER_MOUSE_MOVE_XY:
                browserValue = `${value?.tool_input?.x}, ${value?.tool_input?.y}`
                break
            case TOOL.BROWSER_VIEW_INTERACTIVE_ELEMENTS:
                browserValue = 'View elements'
                break
            case TOOL.BROWSER_SCROLL_DOWN:
            case TOOL.BROWSER_SCROLL_UP:
                browserValue = value?.tool_input?.element || 'Page'
                break
            case TOOL.BROWSER_GET_SELECT_OPTIONS:
            case TOOL.BROWSER_SELECT_DROPDOWN_OPTION:
                browserValue = value?.tool_input?.element || ''
                break
            case TOOL.BROWSER_RESTART:
                browserValue = 'Restart'
                break
            case TOOL.BROWSER_ENTER_TEXT:
                browserValue = value?.tool_input?.text || ''
                break
            case TOOL.BROWSER_ENTER_MULTI_TEXTS:
                {
                    const enterTexts = value?.tool_input?.enter_texts as Array<{
                        text: string
                    }>
                    browserValue = enterTexts
                        ? `${enterTexts.length} fields`
                        : ''
                }
                break
            case TOOL.BROWSER_CLOSE:
            case TOOL.BROWSER_CONSOLE_MESSAGES:
            case TOOL.BROWSER_DRAG:
            case TOOL.BROWSER_EVALUATE:
            case TOOL.BROWSER_HANDLE_DIALOG:
            case TOOL.BROWSER_HOVER:
            case TOOL.BROWSER_NAVIGATE:
            case TOOL.BROWSER_NETWORK_REQUESTS:
            case TOOL.BROWSER_SELECT_OPTION:
            case TOOL.BROWSER_SNAPSHOT:
            case TOOL.BROWSER_WAIT_FOR:
            case TOOL.BROWSER_TAB_CLOSE:
            case TOOL.BROWSER_TAB_LIST:
            case TOOL.BROWSER_TAB_NEW:
            case TOOL.BROWSER_TAB_SELECT:
            case TOOL.BROWSER_SWITCH_TAB:
            case TOOL.BROWSER_OPEN_NEW_TAB:
            case TOOL.VISIT_COMPRESS:
                browserValue = value?.tool_input?.urls?.[0] || ''
                break
            case TOOL.VISIT:
            case TOOL.BROWSER_USE:
                browserValue = value?.tool_input?.url || ''
                break
            case TOOL.IMAGE_GENERATE:
            case TOOL.VIDEO_GENERATE:
            case TOOL.READ_REMOTE_IMAGE:
                browserValue = value?.tool_input?.output_path || ''
                break
            case TOOL.REGISTER_DEPLOYMENT:
                browserValue = value?.tool_input?.url || ''
                break

            default:
                browserValue = ''
        }

        return () => `${buildingTitle} ${browserValue}`
    }, [currentActionData, buildingTitle])

    const searchBrowserProps = useMemo(
        () => ({
            className: tab === 'search_browser' ? 'h-[325px]' : 'hidden',
            keyword:
                currentActionData?.data.tool_input?.query ||
                (currentActionData?.data.tool_input?.queries
                    ? currentActionData?.data.tool_input.queries.join(', ')
                    : undefined),
            search_results:
                (currentActionData?.type === TOOL.WEB_SEARCH ||
                    currentActionData?.type === TOOL.WEB_BATCH_SEARCH) &&
                currentActionData?.data?.result
                    ? parseJson(currentActionData?.data?.result as string)
                    : undefined
        }),
        [currentActionData]
    )

    const browserUrl = useMemo(() => {
        if (currentActionData?.type === TOOL.READ_REMOTE_IMAGE) {
            return currentActionData?.data?.tool_input?.url
        }
        if (
            currentActionData?.type === TOOL.IMAGE_GENERATE ||
            currentActionData?.type === TOOL.VIDEO_GENERATE
        ) {
            const result = currentActionData?.data?.result
            // Handle new dictionary format
            if (
                typeof result === 'object' &&
                result !== null &&
                'url' in result
            ) {
                return (result as FileURLContent).url
            }
            // Fallback for old format
            return result as string
        }
        if (currentActionData?.type === TOOL.BROWSER_TAKE_SCREENSHOT) {
            return currentActionData?.data?.result as string
        }
        return currentActionData?.data?.tool_input?.url
    }, [currentActionData])

    const browserScreenshot = useMemo(() => {
        if (currentActionData?.type === TOOL.READ_REMOTE_IMAGE) {
            return currentActionData?.data?.tool_input?.url
        }
        if (
            currentActionData?.type === TOOL.VISIT ||
            currentActionData?.type === TOOL.VISIT_COMPRESS
        ) {
            return ''
        }
        if (
            currentActionData?.type === TOOL.IMAGE_GENERATE ||
            currentActionData?.type === TOOL.VIDEO_GENERATE
        ) {
            const result = currentActionData?.data?.result
            // For file_url type results, use the URL
            if (
                typeof result === 'object' &&
                result !== null &&
                'url' in result
            ) {
                return (result as FileURLContent).url
            }
            // Fallback for old format
            return result as string
        }
        return typeof currentActionData?.data?.result === 'object'
            ? ((currentActionData?.data?.result as { data: string })
                  ?.data as string)
            : currentActionData?.data?.result
    }, [currentActionData?.data?.result, currentActionData?.type])

    const diffCodeOldContent = useMemo(() => {
        if (
            currentActionData?.data?.tool_name === TOOL.STR_REPLACE_BASED_EDIT
        ) {
            return currentActionData?.data?.tool_input?.old_str as string
        }
        return Array.isArray(currentActionData?.data?.result)
            ? (
                  currentActionData?.data?.result as {
                      old_content: string
                  }[]
              )?.[0]?.old_content || ''
            : ''
    }, [
        currentActionData?.data?.tool_name,
        currentActionData?.data?.result,
        currentActionData?.data?.tool_input?.old_str
    ])

    const diffCodeNewContent = useMemo(() => {
        if (
            currentActionData?.data?.tool_name === TOOL.STR_REPLACE_BASED_EDIT
        ) {
            return currentActionData?.data?.tool_input?.new_str as string
        }

        return Array.isArray(currentActionData?.data?.result)
            ? (
                  currentActionData?.data?.result as {
                      new_content: string
                  }[]
              )?.[0]?.new_content || ''
            : ''
    }, [
        currentActionData?.data?.tool_name,
        currentActionData?.data?.result,
        currentActionData?.data?.tool_input?.new_str
    ])

    const getDeployUrl = (result: string) => {
        const urls = extractUrls(result)
        for (const url of urls) {
            if (url) {
                return url
            }
        }
        return ''
    }

    return (
        <div
            className={`flex-1 flex flex-col justify-between w-full ${className}`}
        >
            <div className={`flex flex-1 flex-col justify-center items-center`}>
                <div className="p-3 md:p-4 w-full md:w-[640px] rounded-xl bg-white dark:bg-[#000000] shadow-btn">
                    <div className={`flex flex-col w-full md:w-[608px]`}>
                        <div className="flex h-8 items-center justify-between gap-2 w-full bg-sky-blue dark:bg-grey rounded-t-xl px-3">
                            <div className="flex items-center gap-1.5">
                                <div className="flex gap-1.5">
                                    <div className="w-3 h-3 rounded-full bg-[#ff5f57]" />
                                    <div className="w-3 h-3 rounded-full bg-[#febc2e]" />
                                    <div className="w-3 h-3 rounded-full bg-[#28c840]" />
                                </div>
                            </div>
                            <div className="flex items-center gap-[6px]">
                                <Icon
                                    name="loading"
                                    className="animate-spin fill-black size-[18px]"
                                />
                                <span className="text-sm font-semibold text-black line-clamp-1 break-all flex-1">
                                    {tab === 'terminal'
                                        ? 'Executing'
                                        : tab === 'browser'
                                          ? getBrowserFileName()
                                          : tab === 'slide'
                                            ? `Generating Slide ${currentActionData?.data?.tool_input?.slide_number || ''}`
                                            : tab === 'deploy'
                                              ? 'Deploying'
                                              : `${buildingTitle} ${last(fileName?.split('/')) || ''}`}
                                </span>
                            </div>
                            <div className="w-12" />
                        </div>
                        <div className="w-full h-[calc((100vw-56px)*9/16)] md:h-[325px] bg-grey dark:bg-black relative rounded-b-xl overflow-hidden">
                            <CodeEditor
                                className={`w-full h-full ${tab === 'code' && isViewTool ? '' : 'hidden'}`}
                                currentActionData={currentActionData}
                                activeFile={fileName}
                                filesContent={{
                                    [fileName || '']: fileContent
                                }}
                                showEditorOnly
                            />
                            <DiffCodeEditor
                                className={`w-full h-full ${tab === 'code' && isEditTool ? '' : 'hidden'}`}
                                activeFile={fileName}
                                oldContent={diffCodeOldContent}
                                newContent={diffCodeNewContent}
                                showEditorOnly
                            />

                            <Browser
                                isHideHeader
                                className={`!h-[calc((100vw-56px)*9/16)] md:!h-[325px] !overflow-auto ${tab === 'browser' ? '!rounded-none' : 'hidden'}`}
                                contentClassName={`bg-grey dark:bg-black h-full ${
                                    currentActionData?.type ===
                                        TOOL.IMAGE_GENERATE ||
                                    currentActionData?.type ===
                                        TOOL.VIDEO_GENERATE ||
                                    currentActionData?.type ===
                                        TOOL.BROWSER_TAKE_SCREENSHOT ||
                                    currentActionData?.type ===
                                        TOOL.READ_REMOTE_IMAGE ||
                                    currentActionData?.type?.startsWith(
                                        'browser'
                                    )
                                        ? '!p-0'
                                        : ''
                                }`}
                                markdownClassName="overflow-visible h-full"
                                url={browserUrl}
                                isVideoUrl={
                                    currentActionData?.type ===
                                    TOOL.VIDEO_GENERATE
                                }
                                screenshot={browserScreenshot}
                                screenshotClassName="w-full h-full object-cover object-top !rounded-none overflow-hidden"
                                raw={
                                    currentActionData?.type === TOOL.VISIT ||
                                    currentActionData?.type ===
                                        TOOL.VISIT_COMPRESS
                                        ? (currentActionData?.data
                                              ?.result as string)
                                        : undefined
                                }
                            />

                            {tab === 'deploy' && (
                                <div className="relative w-full h-full">
                                    <iframe
                                        src={getDeployUrl(
                                            currentActionData?.data
                                                ?.result as string
                                        )}
                                        className="w-full h-full"
                                    />
                                    <Button
                                        className="absolute bottom-4 left-4 shadow-btn bg-white text-black text-xs font-semibold rounded-3xl px-3 py-1 !h-6"
                                        onClick={() =>
                                            window.open(
                                                getDeployUrl(
                                                    currentActionData?.data
                                                        ?.result as string
                                                ),
                                                '_blank'
                                            )
                                        }
                                    >
                                        <Icon
                                            name="export"
                                            className="size-4"
                                        />{' '}
                                        Open in New Tab
                                    </Button>
                                </div>
                            )}

                            {tab === 'image_browser' && (
                                <div className="grid grid-cols-2 gap-2 h-full overflow-auto">
                                    {Array.isArray(searchImages) &&
                                        searchImages
                                            ?.slice(0, 4)
                                            ?.map(({ image_url }, index) => (
                                                <img
                                                    key={index}
                                                    src={image_url}
                                                    alt={`Image ${index + 1}`}
                                                    className="w-full aspect-[374/254] object-cover"
                                                />
                                            ))}
                                </div>
                            )}
                            <Terminal
                                className={`max-h-[325px] !p-0 ${tab === 'terminal' ? '' : 'hidden'}`}
                                currentActionData={currentActionData}
                            />
                            <SearchBrowser {...searchBrowserProps} />
                            {tab === 'slide' && (
                                <div
                                    className="w-full h-full md:max-h-[325px]"
                                    style={
                                        isMobile
                                            ? {
                                                  transform: `scale(${(windowWidth * 0.62) / 430})`,
                                                  transformOrigin: 'top left',
                                                  width: `calc(100vw - 56px)`
                                              }
                                            : {}
                                    }
                                >
                                    <iframe
                                        srcDoc={
                                            (
                                                currentActionData?.data
                                                    ?.result as {
                                                    content: string
                                                }
                                            )?.content ||
                                            (currentActionData?.data?.result &&
                                                Array.isArray(
                                                    currentActionData?.data
                                                        ?.result
                                                ) &&
                                                (
                                                    currentActionData?.data
                                                        ?.result?.[0] as {
                                                        new_content: string
                                                    }
                                                )?.new_content) ||
                                            ''
                                        }
                                        className="w-[1280px] h-[720px]"
                                        style={{
                                            transform: 'scale(0.475)',
                                            transformOrigin: 'top left'
                                        }}
                                    />
                                </div>
                            )}
                        </div>
                    </div>
                    <AgentController />
                </div>
                <p className="text-xs dark:text-white font-semibold text-center mt-4">
                    Once finished, your app screen will be placed here
                </p>
            </div>
            {/* <div className="flex flex-col items-center justify-center p-6 bg-firefly/10 dark:bg-sky-blue/10 rounded-xl dark:text-white w-full max-w-[580px]">
                <p className="text-2xl font-semibold">
                    I’ll take 10-25 minutes to build
                </p>
                <p className="text-2xl font-semibold">as per your request.</p>
                <p className="mt-4 text-sm">
                    I build well-researched, well-designed, well-written,
                </p>
                <p className="text-sm">and functional solutions each time.</p>
            </div> */}
        </div>
    )
}

export default AgentBuild
