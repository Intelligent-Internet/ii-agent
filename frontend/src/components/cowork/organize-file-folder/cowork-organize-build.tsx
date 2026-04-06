import type { ActionStep } from '@/typings/agent'
import type {
    CoworkChatSessionDetail,
    CoworkLiveSessionState
} from '@/typings/cowork'
import CoworkBuildPanel from '../cowork-build/cowork-build-panel'
import { pickCoworkBuildRenderers } from '../cowork-build/cowork-build.renderers'
import {
    CoworkBuildController,
    CoworkBuildViewport,
    useCoworkBuildState
} from '../cowork-build/cowork-build.shared'

interface CoworkOrganizeBuildProps {
    session?: CoworkChatSessionDetail | null
    liveSession?: CoworkLiveSessionState | null
    isRunning?: boolean
    requestedAction?: ActionStep | null
    requestedActionToken?: number
}

const organizeBuildRenderers = pickCoworkBuildRenderers('terminal', 'code')

const CoworkOrganizeBuild = ({
    session = null,
    liveSession = null,
    requestedAction = null,
    requestedActionToken = 0
}: CoworkOrganizeBuildProps) => {
    const buildState = useCoworkBuildState({
        liveSession,
        requestedAction,
        requestedActionToken
    })
    const isAwaitingNextAction =
        buildState.isAwaitingTurnAction && buildState.hasActionHistory
    const headerLabel =
        buildState.currentAction?.data.tool_display_name ||
        buildState.currentAction?.data.tool_name ||
        (session?.run_status === 'completed'
            ? 'Organize run completed'
            : isAwaitingNextAction
              ? 'Generating'
              : 'Cowork build')

    return (
        <CoworkBuildPanel
            headerLabel={headerLabel}
            viewport={
                <CoworkBuildViewport
                    state={buildState}
                    renderers={organizeBuildRenderers}
                    renderUnsupportedAction
                    unsupportedMessage="This organize event does not have a dedicated build renderer yet."
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
            footerText="Browse organize events one step at a time."
        />
    )
}

export default CoworkOrganizeBuild
