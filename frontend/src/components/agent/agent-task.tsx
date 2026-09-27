import { selectMessages, useAppSelector, selectIsStopped } from '@/state'
import clsx from 'clsx'
import { countBy, findLast } from 'lodash'
import { useMemo } from 'react'
import { Icon } from '../ui/icon'
import { Progress } from '../ui/progress'
import { Skeleton } from '../ui/skeleton'
import { Message, Plan, TOOL } from '@/typings'
import { useTranslation } from 'react-i18next'

interface AgentTasksProps {
    className?: string
}

const AgentTasks = ({ className }: AgentTasksProps) => {
    const { t } = useTranslation()
    const messages = useAppSelector(selectMessages)
    const isStopped = useAppSelector(selectIsStopped)

    // Single source of truth: derive plans from the latest TODO_WRITE.
    // No useState/useEffect setState cascade -- previously two effects
    // wrote to each other's input on every messages tick, which can
    // trigger React error #185 ("Maximum update depth exceeded") under
    // chatty agent streams.
    const plans = useMemo<Plan[]>(() => {
        const sourcePlans: Plan[] =
            findLast(
                messages,
                (m: Message) => m?.action?.type === TOOL.TODO_WRITE
            )?.action?.data?.tool_input?.todos || []

        if (
            isStopped ||
            sourcePlans.length === 0 ||
            sourcePlans.some((p) => p.status === 'in_progress')
        ) {
            return sourcePlans
        }

        // Auto-promote the first pending plan to in_progress for display.
        const firstPendingIndex = sourcePlans.findIndex(
            (p) => p.status === 'pending'
        )
        if (firstPendingIndex === -1) return sourcePlans

        const next = sourcePlans.slice()
        next[firstPendingIndex] = {
            ...next[firstPendingIndex],
            status: 'in_progress'
        }
        return next
    }, [messages, isStopped])

    const inProgressPlans = useMemo(
        () => (isStopped ? 0 : countBy(plans, 'status').in_progress || 0),
        [plans, isStopped]
    )

    const completedPlans = useMemo(
        () => countBy(plans, 'status').completed || 0,
        [plans]
    )

    if (plans.length === 0) return null

    return (
        <div
            className={`flex flex-col items-center justify-center w-full ${className}`}
        >
            <p className="text-lg md:text-[32px] font-semibold dark:text-white">
                {isStopped ? t('agent.tasks.stopped', 'Stopped') : t('agent.tasks.inProgress')}
            </p>
            <div className="mt-6 flex flex-col max-w-[580px] gap-y-4 w-full">
                <div className="flex flex-col gap-y-4 max-h-[calc(100vh-350px)] overflow-auto">
                    {plans?.length === 0
                        ? // Loading skeleton when plans is empty
                          Array.from({ length: 4 }).map((_, index) => (
                              <div
                                  key={index}
                                  className="flex items-center justify-between rounded-xl bg-firefly/10 dark:bg-sky-blue/10"
                              >
                                  <div className="flex items-center gap-x-6 flex-1">
                                      <Skeleton className="h-12 w-full" />
                                  </div>
                              </div>
                          ))
                        : Array.isArray(plans) &&
                          plans?.map((plan) => (
                              <div
                                  key={plan.id}
                                  className={clsx(
                                      'flex items-center justify-between px-4 md:px-6 py-3 rounded-xl gap-x-1',
                                      {
                                          'bg-firefly text-white dark:bg-sky-blue dark:text-black':
                                              plan.status === 'completed',
                                          'bg-firefly/10 dark:bg-sky-blue/10 text-[#8b8b8b] dark:text-white':
                                              plan.status !== 'completed'
                                      }
                                  )}
                              >
                                  <div className="flex items-center gap-x-6 flex-1">
                                      {/* <Icon
                                    name={plan.icon}
                                    className={clsx('size-6', {
                                        'stroke-black': plan.status === 'completed',
                                        'stroke-sky-blue':
                                            plan.status !== 'completed'
                                    })}
                                /> */}
                                      <p className="text-xs md:text-sm font-semibold">
                                          {plan.content?.replace(
                                              /^\*\*|\*\*$/g,
                                              ''
                                          )}
                                      </p>
                                  </div>
                                  {plan.status === 'completed' && (
                                      <Icon
                                          name="tick-circle"
                                          className="size-6"
                                      />
                                  )}
                                  {plan.status === 'in_progress' && (
                                      <Icon
                                          name="loading"
                                          className="animate-spin fill-firefly dark:fill-white"
                                      />
                                  )}
                              </div>
                          ))}
                </div>
                <div className="mt-2 w-full">
                    <div className="flex items-center justify-between">
                        <p className="text-sm font-semibold pl-3 md:pl-6">
                            {t('agent.tasks.progress')}
                        </p>
                        <p className="text-sm">
                            <span className="font-semibold">
                                {completedPlans}
                            </span>{' '}
                            / {plans.length}
                        </p>
                    </div>
                    <Progress
                        value={
                            plans.length > 0
                                ? (completedPlans * 100 +
                                      inProgressPlans * 50) /
                                  plans.length
                                : 0
                        }
                        className="mt-3"
                    />
                </div>
            </div>
        </div>
    )
}

export default AgentTasks
