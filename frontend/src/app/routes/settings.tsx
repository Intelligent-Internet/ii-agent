import clsx from 'clsx'
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { useTranslation } from 'react-i18next'

import AccountTab from '@/components/settings/account-tab'
import GeneralTab from '@/components/settings/general-tab'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/ui/icon'
import DataControlTab from '@/components/settings/data-control-tab'
import PersonalizationTab from '@/components/settings/personalization-tab'
import CreditUsage from '@/components/credit-usage'
import SubscriptionTab from '@/components/settings/subscription-tab'
import { Logo } from '@/components/logo'
import { authService } from '@/services/auth.service'
import { setUser } from '@/state/slice/user'
import { useAppDispatch } from '@/state'
import { useIsSageTheme } from '@/hooks/use-is-sage-theme'

enum SettingTab {
    GENERAL = 'general',
    PERSONALIZATION = 'personalization',
    ACCOUNT = 'account',
    NOTIFICATIONS = 'notifications',
    CONNECTORS = 'connectors',
    DATA_CONTROLS = 'data-controls',
    USAGE = 'usage',
    SUBSCRIPTION = 'subscription'
}

const Settings = () => {
    const { t } = useTranslation()
    const dispatch = useAppDispatch()
    const navigate = useNavigate()
    const { tab } = useParams<{ tab?: string }>()
    const isSage = useIsSageTheme()

    const [activeTab, setActiveTab] = useState<SettingTab>(SettingTab.GENERAL)

    const tabs = [
        { key: SettingTab.GENERAL, label: t('settings.tabs.general') },
        { key: SettingTab.PERSONALIZATION, label: t('settings.tabs.personalization') },
        { key: SettingTab.ACCOUNT, label: t('settings.tabs.account') },
        // { key: SettingTab.NOTIFICATIONS, label: t('settings.tabs.notifications') },
        // { key: SettingTab.CONNECTORS, label: t('settings.tabs.connectors') },
        {
            key: SettingTab.DATA_CONTROLS,
            label: t('settings.tabs.dataControls')
        },
        { key: SettingTab.USAGE, label: t('settings.tabs.usage') },
        { key: SettingTab.SUBSCRIPTION, label: t('settings.tabs.subscription') }
    ]

    const handleBack = () => {
        navigate('/')
    }

    const renderTabContent = () => {
        switch (activeTab) {
            case SettingTab.GENERAL:
                return <GeneralTab />
            case SettingTab.PERSONALIZATION:
                return <PersonalizationTab />
            case SettingTab.ACCOUNT:
                return <AccountTab />
            case SettingTab.DATA_CONTROLS:
                return <DataControlTab />
            case SettingTab.USAGE:
                return <CreditUsage />
            case SettingTab.SUBSCRIPTION:
                return <SubscriptionTab />
            default:
                return (
                    <div className="text-center py-8 text-muted-foreground">
                        {t('common.comingSoon')}
                    </div>
                )
        }
    }

    useEffect(() => {
        if (tab && Object.values(SettingTab).includes(tab as SettingTab)) {
            setActiveTab(tab as SettingTab)
        }
    }, [tab])

    useEffect(() => {
        ;(async () => {
            if (tab === SettingTab.SUBSCRIPTION) {
                const userRes = await authService.getCurrentUser()
                dispatch(setUser(userRes))
            }
        })()
    }, [tab])

    return (
        <div className="p-3 md:p-0 min-h-screen bg-background">
            <div className="hidden md:flex px-6 pt-8 pb-6">
                <Logo
                    className="gap-x-3"
                    imageClassName={`${isSage ? '!h-6 md:!h-8' : 'size-10'} inline`}
                    label="II-Agent"
                    labelClassName="text-black dark:text-white text-2xl font-semibold"
                />
            </div>

            <div className="max-w-3xl mx-auto md:pb-8">
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-x-3 md:gap-x-4">
                        <button className="cursor-pointer" onClick={handleBack}>
                            <Icon
                                name="arrow-left"
                                className="size-8 hidden dark:inline"
                            />
                            <Icon
                                name="arrow-left-dark"
                                className="size-8 inline dark:hidden"
                            />
                        </button>
                        <span className="text-black dark:text-sky-blue text-2xl md:text-[32px] font-semibold">
                            {t('settings.title')}
                        </span>
                    </div>
                </div>

                <div className="space-y-8 mt-5">
                    <div className="flex items-center gap-x-2 md:flex-wrap overflow-x-auto no-scrollbar md:with-scrollbar">
                        {tabs.map((tab) => (
                            <Button
                                key={tab.key}
                                className={clsx(
                                    'h-7 text-xs font-semibold px-4 rounded-full border border-sky-blue',
                                    {
                                        'bg-firefly border-firefly dark:border-sky-blue-2 dark:bg-sky-blue text-sky-blue-2 dark:text-black':
                                            activeTab === tab.key,
                                        'dark:border-sky-blue border-firefly dark:text-sky-blue':
                                            activeTab !== tab.key
                                    }
                                )}
                                onClick={() => {
                                    setActiveTab(tab.key)
                                    navigate(`/settings/${tab.key}`, {
                                        replace: true
                                    })
                                }}
                            >
                                {tab.label}
                            </Button>
                        ))}
                    </div>

                    <div className="mt-6 md:mt-8">{renderTabContent()}</div>
                </div>
            </div>
        </div>
    )
}

export { Settings as Component }
