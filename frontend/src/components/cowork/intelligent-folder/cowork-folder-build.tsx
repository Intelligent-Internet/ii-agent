import type { ActionStep } from '@/typings/agent'
import type {
    CoworkChatSessionDetail,
    CoworkLiveSessionState
} from '@/typings/cowork'
import { formatCoworkBuildHeaderLabel } from '../cowork-action-utils'
import CoworkBuildPanel from '../cowork-build/cowork-build-panel'
import { pickCoworkBuildRenderers } from '../cowork-build/cowork-build.renderers'
import {
    CoworkBuildController,
    CoworkBuildViewport,
    useCoworkBuildState
} from '../cowork-build/cowork-build.shared'

interface CoworkFolderBuildProps {
    session?: CoworkChatSessionDetail | null
    liveSession?: CoworkLiveSessionState | null
    isRunning?: boolean
    requestedAction?: ActionStep | null
    requestedActionToken?: number
}

const folderBuildRenderers = pickCoworkBuildRenderers(
    'desktopTool',
    'terminal',
    'code'
)

const CoworkFolderBuild = ({
    session = null,
    liveSession = null,
    requestedAction = null,
    requestedActionToken = 0
}: CoworkFolderBuildProps) => {
    const buildState = useCoworkBuildState({
        liveSession,
        requestedAction,
        requestedActionToken
    })
    const isAwaitingNextAction =
        buildState.isAwaitingTurnAction && buildState.hasActionHistory
    const headerLabel =
        formatCoworkBuildHeaderLabel(buildState.currentAction) ||
        buildState.currentAction?.data.tool_name ||
        (session?.run_status === 'completed'
            ? 'Intelligent Folder run completed'
            : isAwaitingNextAction
              ? 'Generating'
              : 'Cowork build')

    return (
        <CoworkBuildPanel
            headerLabel={headerLabel}
            viewport={
                <CoworkBuildViewport
                    state={buildState}
                    renderers={folderBuildRenderers}
                    renderUnsupportedAction
                    unsupportedMessage="This Intelligent Folder event does not have a dedicated build renderer yet."
                    emptyTitle={
                        isAwaitingNextAction
                            ? 'Generating'
                            : 'Waiting for build events'
                    }
                />
            }
            controller={
                <CoworkBuildController
                    step={buildState.step}
                    totalSteps={buildState.totalSteps}
                    isLiveUpdate={buildState.isLiveUpdate}
                    onStepChange={buildState.setStep}
                    onJumpToLatest={buildState.jumpToLatest}
                />
            }
            footerText="Browse Intelligent Folder events one step at a time."
        />
    )
}

export default CoworkFolderBuild
