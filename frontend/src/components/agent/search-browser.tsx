import React from 'react'
import { useTranslation } from 'react-i18next'

type SearchResultItem = {
    url?: string
    title?: string
}

interface SearchBrowserProps {
    className?: string
    keyword?: string
    search_results?:
        | string
        | Record<string, unknown>
        | Record<string, unknown>[]
        | undefined
}

const SearchBrowser = React.memo(
    ({ className, keyword, search_results }: SearchBrowserProps) => {
        const { t } = useTranslation()
        if (!keyword) return
        const items = Array.isArray(search_results)
            ? (search_results as SearchResultItem[])
            : []

        return (
            <div
                className={`flex-1 bg-grey dark:bg-black px-3 md:px-4 divide-y divide-grey-2/30 dark:divide-white/30 overflow-auto ${className}`}
            >
                <div className="space-y-3 py-4">
                    {items.length > 0 && (
                            <p className="text-sm font-semibold">
                                {t('agent.searchBrowser.resultsCount', {
                                    count: items.length
                                })}
                            </p>
                        )}
                    {items.map((item, index) => (
                            <div
                                key={index}
                                className="flex flex-col py-3 px-3 md:px-4 bg-firefly dark:bg-sky-blue rounded-xl shadow-btn"
                            >
                                <a
                                    href={item.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="font-semibold text-white dark:text-black hover:underline text-xs line-clamp-1 break-all"
                                >
                                    {item.url ?? ''}
                                </a>
                                <span className="text-white dark:text-black text-xs line-clamp-1 break-all">
                                    {item.title ?? ''}
                                </span>
                            </div>
                        ))}
                </div>
            </div>
        )
    }
)

SearchBrowser.displayName = 'SearchBrowser'

export default SearchBrowser
