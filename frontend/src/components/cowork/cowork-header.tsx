import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import ButtonIcon from '@/components/button-icon'
import { Logo } from '@/components/logo'
import { ENABLE_BETA } from '@/constants/features'
import { useIsSageTheme } from '@/hooks/use-is-sage-theme'

const CoworkHeader = () => {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const isSage = useIsSageTheme()

    return (
        <div className="relative flex items-center gap-x-4 border-b border-neutral-200 px-3 py-3 dark:border-white/30 md:px-6">
            <ButtonIcon
                name="home"
                className="bg-black"
                iconClassName="fill-sky-blue-2 dark:fill-black"
                onClick={() => navigate('/')}
            />
            <Logo
                className="gap-x-[6px]"
                imageClassName={`${isSage ? '!h-6 md:!h-6' : 'size-6'} inline`}
                alt={t('publicHome.logoAlt')}
                label={t('common.appName')}
                labelClassName="text-sm font-semibold text-black dark:text-white"
                showBeta={ENABLE_BETA}
                betaLabel={t('common.beta')}
            />
            <div className="pointer-events-none absolute inset-x-0 flex justify-center px-20">
                <span className="truncate rounded-full border border-charcoal bg-charcoal px-4 py-1.5 text-sm font-semibold text-sky-blue-2 shadow-sm dark:border-sky-blue-2 dark:bg-sky-blue dark:text-black">
                    II-Cowork
                </span>
            </div>
        </div>
    )
}

export default CoworkHeader
