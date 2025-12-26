import { selectMessages, useAppDispatch, useAppSelector, selectIsStopped } from '@/state'
import clsx from 'clsx'
import { countBy, findLast } from 'lodash'
import { useEffect, useMemo, useState } from 'react'
import { Icon } from '../ui/icon'
import { Progress } from '../ui/progress'
import { Skeleton } from '../ui/skeleton'
import { Message, Plan, TOOL } from '@/typings'

interface AgentTasksProps {
    className?: string
}

const AgentTasks = ({ className }: AgentTasksProps) => {
    const messages = useAppSelector(selectMessages)
    const isStopped = useAppSelector(selectIsStopped)
    const dispatch = useAppDispatch()
    const [plans, setPlans] = useState<Plan[]>([])

    useEffect(() => {
        setPlans(
            findLast(
                messages,
                (m: Message) => m?.action?.type === TOOL.TODO_WRITE
            )?.action?.data?.tool_input?.todos || []
        )
    }, [messages])

    useEffect(() => {
        // Don't auto-promote tasks if the agent is stopped
        if (isStopped) return

        // Check if there are no in_progress tasks
        const hasInProgress = plans.some(
            (plan) => plan.status === 'in_progress'
        )

        if (!hasInProgress && plans.length > 0) {
            // Find the first pending task
            const firstPendingIndex = plans.findIndex(
                (plan) => plan.status === 'pending'
            )

            if (firstPendingIndex !== -1) {
                const updatedPlans = [...plans]
                updatedPlans[firstPendingIndex] = {
                    ...updatedPlans[firstPendingIndex],
                    status: 'in_progress'
                }
                setPlans(updatedPlans)
            }
        }
    }, [plans, dispatch, isStopped])

    const inProgressPlans = useMemo(
        () => isStopped ? 0 : (countBy(plans, 'status').in_progress || 0),
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
                {isStopped ? 'Stopped' : 'In progress'}
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
                                          {plan.content.replace(
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
                            Task Progress
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
