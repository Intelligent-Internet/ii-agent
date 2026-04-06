import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Switch } from '../ui/switch'
import MemoryTable from './memory-table'
import { useAppDispatch, useAppSelector } from '@/state/store'
import { selectUserPreferences, setUser } from '@/state/slice/user'
import { userService } from '@/services/user.service'
import { authService } from '@/services/auth.service'
import { toast } from 'sonner'

const PersonalizationTab = () => {
    const { t } = useTranslation()
    const dispatch = useAppDispatch()
    const preferences = useAppSelector(selectUserPreferences)

    const [hasMemory, setHasMemory] = useState(preferences.has_memory)

    useEffect(() => {
        setHasMemory(preferences.has_memory)
    }, [preferences.has_memory])

    const handleToggle = async (value: boolean) => {
        setHasMemory(value)
        try {
            await userService.updatePreferences({ has_memory: value })
            const userRes = await authService.getCurrentUser()
            dispatch(setUser(userRes))
        } catch {
            setHasMemory(!value)
            toast.error(t('errors.generic'))
        }
    }

    return (
        <div>
            <div className="divide-y divide-white/30">
                <div className="flex flex-col md:flex-row md:items-center gap-4 justify-between pb-6">
                    <div>
                        <h2 className="text-[18px] font-semibold mb-1">
                            {t('settings.personalization.referenceMemories')}
                        </h2>
                        <p className="text-xs max-w-[332px]">
                            {t(
                                'settings.personalization.referenceMemoriesDescription'
                            )}
                        </p>
                    </div>
                    <Switch
                        checked={hasMemory}
                        onCheckedChange={handleToggle}
                    />
                </div>
            </div>
            <div className="mt-8">
                <MemoryTable />
            </div>
        </div>
    )
}

export default PersonalizationTab