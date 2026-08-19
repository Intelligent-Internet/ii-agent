import { useMemo } from 'react'
import clsx from 'clsx'
import { toast } from 'sonner'
import { useLocation } from 'react-router'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { PublishButton } from '@/components/agent/publish-button'
import { MobilePublishButton } from '@/components/agent/mobile-publish-button'
import {
    selectActiveTab,
    selectVscodeUrl,
    selectVncUrl,
    setActiveTab,
    useAppDispatch,
    useAppSelector
} from '@/state'
import { AGENT_TYPE, TAB } from '@/typings/agent'

interface AgentTabsProps {
    sessionId?: string
    projectId?: string | null
    agentType?: string
}

const AgentTabs = ({ sessionId, projectId, agentType }: AgentTabsProps) => {
    const { t } = useTranslation()
    const dispatch = useAppDispatch()
    const location = useLocation()

    const activeTab = useAppSelector(selectActiveTab)
    const vscodeUrl = useAppSelector(selectVscodeUrl)
    const vncUrl = useAppSelector(selectVncUrl)

    const isShareMode = useMemo(
        () => location.pathname.includes('/share/'),
        [location.pathname]
    )

    const handleOpenVSCode = () => {
        if (!vscodeUrl) {
            toast.error(t('agentTab.errors.vscodeUrlMissing'))
            return
        }

        window.open(vscodeUrl, '_blank')
    }

    const handleOpenVNC = () => {
        if (!vncUrl) {
            toast.error(t('agentTab.errors.vncUrlMissing', 'noVNC URL not available'))
            return
        }

        window.open(vncUrl, '_blank')
    }

    const shouldShowProjectTab = useMemo(() => {
        if (isShareMode) {
            return false
        }
        return Boolean(sessionId && projectId)
    }, [isShareMode, sessionId, projectId])

    const tabs = useMemo(() => {
        const base = [
            {
                id: TAB.BUILD,
                labelKey: 'agentTab.tabs.build',
                hidden: false
            },
            { id: TAB.RESULT, labelKey: 'agentTab.tabs.result', hidden: false }
        ]

        if (shouldShowProjectTab) {
            base.push({
                id: TAB.PROJECT,
                labelKey: 'agentTab.tabs.project',
                hidden: false
            })
        }

        return base.filter((tab) => !tab.hidden)
    }, [isShareMode, shouldShowProjectTab])

    const getButtonClasses = (tabId: TAB) => {
        const isActive = activeTab === tabId
        return clsx(
            'h-7 text-xs font-semibold px-4 rounded-full border border-sky-blue transition-colors',
            {
                'bg-firefly border-firefly dark:border-sky-blue-2 dark:bg-sky-blue text-sky-blue-2 dark:text-black':
                    isActive,
                'dark:border-sky-blue border-firefly dark:text-sky-blue':
                    !isActive
            }
        )
    }

    return (
        <div className="hidden md:flex items-center justify-between px-6 py-4 border-b border-neutral-200 dark:border-white/30">
            <div className="flex items-center gap-x-2">
                {tabs.map((tab) => (
                    <Button
                        key={tab.id}
                        className={getButtonClasses(tab.id)}
                        onClick={() => dispatch(setActiveTab(tab.id))}
                    >
                        {t(tab.labelKey)}
                    </Button>
                ))}
            </div>
            <div className="flex items-center gap-4">
                {vscodeUrl && !isShareMode && (
                    <Button
                        className="rounded-full h-7 text-xs font-semibold border-black dark:border-white"
                        variant="outline"
                        onClick={handleOpenVSCode}
                    >
                        <img
                            src={'/images/vscode.png'}
                            alt={t('agentTab.vscodeAlt')}
                            width={16}
                            height={16}
                        />{' '}
                        {t('agentTab.openInVSCode')}
                    </Button>
                )}
                {vncUrl && !isShareMode && (
                    <Button
                        className="rounded-full h-7 text-xs font-semibold border-black dark:border-white"
                        variant="outline"
                        onClick={handleOpenVNC}
                    >
                        🖥️ {t('agentTab.openBrowserVNC', 'View Browser')}
                    </Button>
                )}
                {agentType === AGENT_TYPE.MOBILE_APP ? (
                    <MobilePublishButton
                        size="sm"
                        className="bg-sky-blue text-charcoal !h-6"
                    />
                ) : (
                    <PublishButton
                        size="sm"
                        className="bg-sky-blue text-charcoal !h-6"
                    />
                )}
            </div>
        </div>
    )
}

export default AgentTabs
