'use client'

import { useState } from 'react'
import { useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'
import clsx from 'clsx'

import { Logo } from '@/components/logo'
import { Icon } from '@/components/ui/icon'
import {
    SidebarProvider,
    SidebarTrigger
} from '@/components/ui/sidebar'
import Sidebar from '@/components/sidebar'
import { useIsSageTheme } from '@/hooks/use-is-sage-theme'
import { useIsMobile } from '@/hooks/use-mobile'
import { ChannelsPanel } from '@/components/ii-claw/channels'
import { CronJobsPanel } from '@/components/ii-claw/cron-jobs'
import { AgentsPanel } from '@/components/ii-claw/agents'

type ClawTab = 'agents' | 'channels' | 'cronjobs'

const CLAW_SIDEBAR_ITEMS: {
    key: ClawTab
    label: string
    iconName: string
    i18nKey: string
}[] = [
    { key: 'agents', label: 'Agents', iconName: 'agent', i18nKey: 'iiClaw.agents.title' },
    { key: 'channels', label: 'Channels', iconName: 'connector', i18nKey: 'iiClaw.channels.title' },
    { key: 'cronjobs', label: 'Cron Jobs', iconName: 'clock', i18nKey: 'iiClaw.cronJobs.title' },
]

// ---------------------------------------------------------------------------
// Desktop Sidebar
// ---------------------------------------------------------------------------

const ClawDesktopSidebar = ({
    activeTab,
    setActiveTab,
    handleBack,
    isSage
}: {
    activeTab: ClawTab
    setActiveTab: (tab: ClawTab) => void
    handleBack: () => void
    isSage: boolean
}) => {
    const { t } = useTranslation()

    return (
        <div className="hidden md:flex w-64 shrink-0 border-r border-grey-2 dark:border-grey/30 bg-sidebar-bg dark:bg-charcoal flex-col">
            <div className="p-6 pb-4">
                <div className="flex items-center gap-3 mb-6">
                    <button className="cursor-pointer" onClick={handleBack}>
                        <Icon name="arrow-left" className="size-5 hidden dark:inline" />
                        <Icon name="arrow-left-dark" className="size-5 inline dark:hidden" />
                    </button>
                    <Logo
                        className="gap-x-2"
                        imageClassName={clsx('rounded-sm', isSage ? '!h-5' : 'size-7')}
                        label={t('iiClaw.title')}
                        labelClassName="text-black dark:text-white text-lg font-bold"
                        width={28}
                        height={28}
                    />
                </div>
            </div>

            <nav className="flex-1 px-3">
                {CLAW_SIDEBAR_ITEMS.map((item) => (
                    <button
                        key={item.key}
                        onClick={() => setActiveTab(item.key)}
                        className={clsx(
                            'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors cursor-pointer',
                            {
                                'bg-sky-blue/30 text-black dark:bg-sky-blue/15 dark:text-white':
                                    activeTab === item.key,
                                'text-black/90 dark:text-white/90 hover:text-black dark:hover:text-white hover:bg-sky-blue/10 dark:hover:bg-sky-blue/10':
                                    activeTab !== item.key
                            }
                        )}
                    >
                        <Icon
                            name={item.iconName}
                            className={clsx('size-5', {
                                'fill-black dark:fill-white': activeTab === item.key,
                                'fill-black/60 dark:fill-white/60': activeTab !== item.key
                            })}
                        />
                        {t(item.i18nKey)}
                    </button>
                ))}
            </nav>

            <div className="p-4 border-t border-grey-2 dark:border-grey/30">
                <p className="text-xs text-charcoal/30 dark:text-white/20 text-center">
                    {t('iiClaw.version')}
                </p>
            </div>
        </div>
    )
}

// ---------------------------------------------------------------------------
// Mobile Layout
// ---------------------------------------------------------------------------

const IIClawMobile = ({
    activeTab,
    setActiveTab,
    renderContent,
    handleBack
}: {
    activeTab: ClawTab
    setActiveTab: (tab: ClawTab) => void
    renderContent: () => React.ReactNode
    handleBack: () => void
}) => {
    const { t } = useTranslation()

    return (
        <SidebarProvider>
            <Sidebar />
            <div className="flex flex-col min-h-screen w-full bg-white dark:bg-charcoal text-black dark:text-white">
                <div className="flex items-start justify-between px-3 pt-6 pb-3">
                    <div className="flex items-center gap-3">
                        <SidebarTrigger className="size-6 p-0" />
                        <span className="text-lg font-bold text-black dark:text-white leading-tight">
                            {t('iiClaw.title')}
                        </span>
                    </div>
                    <button className="cursor-pointer p-1" onClick={handleBack}>
                        <Icon name="arrow-left" className="size-5 hidden dark:inline" />
                        <Icon name="arrow-left-dark" className="size-5 inline dark:hidden" />
                    </button>
                </div>

                <div className="flex gap-2 px-3 pb-3">
                    {CLAW_SIDEBAR_ITEMS.map((item) => (
                        <button
                            key={item.key}
                            onClick={() => setActiveTab(item.key)}
                            className={clsx(
                                'flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition',
                                {
                                    'bg-firefly dark:bg-sky-blue-2 text-sky-blue-2 dark:text-black':
                                        activeTab === item.key,
                                    'text-black/60 dark:text-white/60':
                                        activeTab !== item.key
                                }
                            )}
                        >
                            <Icon
                                name={item.iconName}
                                className={clsx('size-4', {
                                    'fill-sky-blue-2 dark:fill-black': activeTab === item.key,
                                    'fill-black/60 dark:fill-white/60': activeTab !== item.key
                                })}
                            />
                            {t(item.i18nKey)}
                        </button>
                    ))}
                </div>

                <div className="flex-1 overflow-y-auto">{renderContent()}</div>
            </div>
        </SidebarProvider>
    )
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

const IIClaw = () => {
    const navigate = useNavigate()
    const isSage = useIsSageTheme()
    const isMobile = useIsMobile()
    const [activeTab, setActiveTab] = useState<ClawTab>('agents')

    const handleBack = () => {
        navigate(-1)
    }

    const renderContent = () => {
        switch (activeTab) {
            case 'agents':
                return <AgentsPanel />
            case 'channels':
                return <ChannelsPanel />
            case 'cronjobs':
                return <CronJobsPanel />
            default:
                return null
        }
    }

    if (isMobile) {
        return (
            <IIClawMobile
                activeTab={activeTab}
                setActiveTab={setActiveTab}
                renderContent={renderContent}
                handleBack={handleBack}
            />
        )
    }

    return (
        <div className="flex h-screen bg-white dark:bg-charcoal overflow-hidden text-black dark:text-white">
            <ClawDesktopSidebar
                activeTab={activeTab}
                setActiveTab={setActiveTab}
                handleBack={handleBack}
                isSage={isSage}
            />
            <div className="flex-1 flex flex-col overflow-hidden">
                {renderContent()}
            </div>
        </div>
    )
}

export { IIClaw as Component }
