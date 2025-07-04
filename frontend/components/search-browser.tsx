import React from "react";
import { SearchIcon } from "lucide-react";

interface SearchBrowserProps {
  className?: string;
  keyword?: string;
  search_results?: string | Record<string, unknown> | undefined;
}

const SearchBrowser = React.memo(
  ({ className, keyword, search_results }: SearchBrowserProps) => {
    if (!keyword) return;

    return (
      <div
        className={`h-[calc(100vh-178px)] flex rounded-xl flex-col overflow-hidden border border-[#3A3B3F] ${className}`}
      >
        <div className="flex items-center gap-3 px-3 py-2.5 bg-black/80 backdrop-blur-xl border-b border-neutral-800">
          <div className="flex items-center gap-1.5">
            <div className="flex gap-1.5">
              <div className="w-3 h-3 rounded-full bg-[#ff5f57]" />
              <div className="w-3 h-3 rounded-full bg-[#febc2e]" />
              <div className="w-3 h-3 rounded-full bg-[#28c840]" />
            </div>
          </div>
          <div className="flex-1 flex items-center">
            <div className="bg-[#35363a] px-3 py-1.5 rounded-lg w-full flex items-center gap-2 group transition-colors">
              <SearchIcon className="h-3.5 w-3.5 text-white flex-shrink-0" />
              <span className="text-sm text-white truncate font-medium">
                {keyword}
              </span>
            </div>
          </div>
        </div>
        <div className="flex-1 bg-black/80 px-6 divide-y divide-y-neutral-200 overflow-auto">
          {Array.isArray(search_results) &&
            search_results?.map((item, index) => (
              <div
                key={index}
                className="flex flex-col gap-y-2 py-6 hover:bg-neutral-900 transition-colors"
              >
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-semibold text-blue-400 hover:underline text-lg"
                >
                  {item.title}
                </a>
                <p className="text-neutral-400 text-sm line-clamp-2">
                  {item.content}
                </p>
                <span className="text-green-400 text-xs">{item.url}</span>
              </div>
            ))}
        </div>
      </div>
    );
  }
);

SearchBrowser.displayName = "SearchBrowser";

export default SearchBrowser;
