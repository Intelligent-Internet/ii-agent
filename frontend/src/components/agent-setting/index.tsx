import { Button } from '@/components/ui/button'
import { Icon } from '@/components/ui/icon'
import {
    Sheet,
    SheetClose,
    SheetContent,
    SheetHeader
} from '@/components/ui/sheet'
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription
} from '@/components/ui/dialog'
import { useState } from 'react'
import ModelSetting from './model-setting'
import ToolSetting from './tool-setting'
import SkillSetting from './skill-setting'
import { selectQuestionMode, useAppSelector } from '@/state'
import { QUESTION_MODE } from '@/typings'
import { useTranslation } from 'react-i18next'
import { isAgenticQuestionMode } from '@/utils/question-mode'

enum TABS {
    MODEL = 'model',
    TOOLS = 'tools',
    SKILLS = 'skills'
}

interface AgentSettingProps {
    isOpen: boolean
    onOpenChange: (open: boolean) => void
}

const AgentSetting = ({ isOpen, onOpenChange }: AgentSettingProps) => {
    const { t } = useTranslation()
    const [activeTab, setActiveTab] = useState(TABS.MODEL)
    const [isSkillsHelpOpen, setIsSkillsHelpOpen] = useState(false)
    const questionMode = useAppSelector(selectQuestionMode)
    const isAgenticMode = isAgenticQuestionMode(questionMode)

    const skillExamples = t('agentSetting.skillSetting.help.examples.items', {
        returnObjects: true
    }) as Array<{ name: string; url: string }>

    const tabLabels: Record<TABS, string> = {
        [TABS.MODEL]: t('agentSetting.tabs.model'),
        [TABS.TOOLS]: t('agentSetting.tabs.tools'),
        [TABS.SKILLS]: t('agentSetting.tabs.skills')
    }

    return (
        <Sheet open={isOpen} onOpenChange={onOpenChange}>
            <SheetContent className="pt-0 md:pt-12 w-full !max-w-[560px]">
                <SheetHeader className="px-3 md:px-6 gap-6 pb-4">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-x-3">
                            <SheetClose className="md:hidden cursor-pointer">
                                <Icon
                                    name="close"
                                    className="fill-grey-2 dark:fill-grey"
                                />
                            </SheetClose>
                            <p className="text-2xl font-semibold">
                                {isAgenticMode
                                    ? t('agentSetting.title.agent')
                                    : t('agentSetting.title.chat')}
                            </p>
                        </div>
                        <div className="hidden md:flex items-center gap-x-4">
                            {/* <Button
                                size="sm"
                                className="h-[22px] dark:bg-white/40 rounded-md"
                                onClick={handleReset}
                            >
                                Reset
                            </Button> */}
                            <SheetClose className="cursor-pointer">
                                <Icon
                                    name="close"
                                    className="fill-grey-2 dark:fill-grey"
                                />
                            </SheetClose>
                        </div>
                    </div>
                    <div
                        className={`${questionMode === QUESTION_MODE.CHAT ? 'hidden' : 'flex'} items-center gap-x-2`}
                    >
                        {(Object.values(TABS) as TABS[]).map((tab) => (
                            <Button
                                key={tab}
                                className={`flex-1 border border-firefly dark:border-sky-blue-2 text-base rounded-lg h-10 ${
                                    activeTab === tab
                                        ? 'bg-firefly dark:bg-sky-blue-2 text-sky-blue-2 dark:text-black'
                                        : 'dark:text-sky-blue-2'
                                }`}
                                onClick={() => setActiveTab(tab)}
                            >
                                {tabLabels[tab]}
                            </Button>
                        ))}
                        {activeTab === TABS.SKILLS && (
                            <button
                                onClick={() => setIsSkillsHelpOpen(true)}
                                className="p-1.5 rounded-full bg-firefly/10 dark:bg-sky-blue-2/20 border border-firefly/30 dark:border-sky-blue-2/40 hover:bg-firefly/20 dark:hover:bg-sky-blue-2/30 transition-colors"
                                aria-label={t(
                                    'agentSetting.skillSetting.help.title'
                                )}
                            >
                                <Icon
                                    name="help"
                                    className="size-5 fill-firefly dark:fill-sky-blue-2"
                                />
                            </button>
                        )}
                    </div>
                </SheetHeader>
                <div className="space-y-4 flex-1 overflow-auto px-3 md:px-6 md:pb-12">
                    <ModelSetting
                        className={activeTab === TABS.MODEL ? '' : 'hidden'}
                    />
                    <ToolSetting
                        className={activeTab === TABS.TOOLS ? '' : 'hidden'}
                    />
                    <SkillSetting
                        className={activeTab === TABS.SKILLS ? '' : 'hidden'}
                    />
                </div>
            </SheetContent>

            {/* Skills Help Dialog */}
            <Dialog open={isSkillsHelpOpen} onOpenChange={setIsSkillsHelpOpen}>
                <DialogContent className="max-w-md bg-white dark:bg-white border-gray-200">
                    <DialogHeader>
                        <DialogTitle className="text-black">
                            {t('agentSetting.skillSetting.help.title')}
                        </DialogTitle>
                        <DialogDescription className="text-gray-600">
                            {t('agentSetting.skillSetting.help.description')}
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 mt-2">
                        {/* What are Skills */}
                        <div>
                            <h4 className="font-medium text-sm text-black">
                                {t(
                                    'agentSetting.skillSetting.help.sections.whatAreSkills.title'
                                )}
                            </h4>
                            <p className="text-sm text-gray-600 mt-1">
                                {t(
                                    'agentSetting.skillSetting.help.sections.whatAreSkills.content'
                                )}
                            </p>
                        </div>

                        {/* Where to Find */}
                        <div>
                            <h4 className="font-medium text-sm text-black">
                                {t(
                                    'agentSetting.skillSetting.help.sections.whereToFind.title'
                                )}
                            </h4>
                            <p className="text-sm text-gray-600 mt-1">
                                {t(
                                    'agentSetting.skillSetting.help.sections.whereToFind.content'
                                )}
                            </p>
                        </div>

                        {/* Example Skills */}
                        <div>
                            <h4 className="font-medium text-sm text-black">
                                {t(
                                    'agentSetting.skillSetting.help.examples.title'
                                )}
                            </h4>
                            <div className="flex flex-wrap gap-2 mt-2">
                                {Array.isArray(skillExamples) &&
                                    skillExamples.map((example) => (
                                        <a
                                            key={example.name}
                                            href={example.url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="text-xs px-2 py-1 rounded-md bg-gray-100 text-gray-700 hover:bg-gray-200 transition-colors"
                                        >
                                            {example.name}
                                        </a>
                                    ))}
                            </div>
                        </div>

                        {/* Browse All Link */}
                        <a
                            href={t('agentSetting.skillSetting.help.link.url')}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-2 text-sm text-blue-600 hover:underline mt-4"
                        >
                            <Icon
                                name="link-2"
                                className="size-4 fill-blue-600"
                            />
                            {t('agentSetting.skillSetting.help.link.text')}
                        </a>
                    </div>
                </DialogContent>
            </Dialog>
        </Sheet>
    )
}

export default AgentSetting
