import Image from "next/image";
import { Globe, SquareArrowOutUpRight } from "lucide-react";
import Markdown from "./markdown";

interface BrowserProps {
  className?: string;
  url?: string;
  screenshot?: string;
  rawData?: string;
}

const Browser = ({ className, url, screenshot, rawData }: BrowserProps) => {
  if (!url) return;

  return (
    <div
      className={`h-[calc(100vh-142px)] overflow-hidden border border-neutral-200 dark:border-neutral-800 ${className}`}
    >
      <div className="flex items-center gap-3 px-3 py-2.5 bg-white/80 dark:bg-black/80 backdrop-blur-xl border-b border-neutral-200 dark:border-neutral-800">
        <div className="flex items-center gap-1.5">
          <div className="flex gap-1.5">
            <div className="w-3 h-3 rounded-full bg-[#ff5f57]" />
            <div className="w-3 h-3 rounded-full bg-[#febc2e]" />
            <div className="w-3 h-3 rounded-full bg-[#28c840]" />
          </div>
        </div>
        <div className="flex-1 flex items-center">
          <div className="bg-neutral-100 dark:bg-neutral-800 px-3 py-1.5 rounded-lg w-full flex items-center gap-2 group transition-colors">
            <Globe className="h-3.5 w-3.5 text-neutral-400 dark:text-neutral-500 flex-shrink-0" />
            <span className="text-sm text-neutral-600 dark:text-neutral-400 truncate font-medium">
              {url}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            className="p-1.5 rounded-md hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
            onClick={() => window.open(url, "_blank")}
          >
            <SquareArrowOutUpRight className="h-4 w-4 text-white" />
          </button>
        </div>
      </div>
      {screenshot && (
        <Image
          src={screenshot}
          alt="Browser"
          width={1000}
          height={1000}
          className="w-full h-full object-contain object-top"
        />
      )}
      {rawData && (
        <div className="p-4">
          <Markdown>{rawData}</Markdown>
        </div>
      )}
    </div>
  );
};

export default Browser;
