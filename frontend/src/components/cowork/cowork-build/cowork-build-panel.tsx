import type { ReactNode } from 'react'
import { Icon } from '@/components/ui/icon'

interface CoworkBuildPanelProps {
    headerLabel: string
    viewport: ReactNode
    controller?: ReactNode
    footerText?: string
}

const CoworkBuildPanel = ({
    headerLabel,
    viewport,
    controller,
    footerText
}: CoworkBuildPanelProps) => {
    return (
        <div className="flex-1 flex flex-col justify-between w-full">
            <div className="flex flex-1 flex-col justify-center items-center">
                <div className="w-full max-w-[760px] rounded-xl bg-white p-3 shadow-btn dark:bg-[#000000] md:p-4">
                    <div className="flex w-full flex-col">
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
                                    {headerLabel}
                                </span>
                            </div>
                            <div className="w-12" />
                        </div>
                        <div className="relative w-full overflow-hidden rounded-b-xl bg-grey aspect-video dark:bg-black">
                            {viewport}
                        </div>
                    </div>
                    {controller}
                </div>
                {footerText && (
                    <p className="text-xs dark:text-white font-semibold text-center mt-4">
                        {footerText}
                    </p>
                )}
            </div>
        </div>
    )
}

export default CoworkBuildPanel
