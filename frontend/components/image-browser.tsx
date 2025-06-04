import { Globe } from "lucide-react";

interface BrowserProps {
  className?: string;
  url?: string;
  images?: string[];
}

const ImageBrowser = ({ className, url, images = [] }: BrowserProps) => {
  if (!url && !images?.length) return null;

  return (
    <div
      className={`h-[calc(100vh-178px)] border border-[#3A3B3F] rounded-xl overflow-hidden shadow-sm ${className}`}
    >
      <div className="flex items-center gap-3 px-3 py-2.5 bg-black/80 border-b border-neutral-800">
        <div className="flex items-center gap-1.5">
          <div className="flex gap-1.5">
            <div className="w-3 h-3 rounded-full bg-[#ff5f57]" />
            <div className="w-3 h-3 rounded-full bg-[#febc2e]" />
            <div className="w-3 h-3 rounded-full bg-[#28c840]" />
          </div>
        </div>
        <div className="flex-1 flex items-center overflow-hidden">
          <div className="bg-[#35363a] px-3 py-1.5 rounded-lg w-full flex items-center gap-2 group transition-colors">
            <Globe className="h-3.5 w-3.5 text-white flex-shrink-0" />
            <span className="text-sm text-white truncate flex-1 font-medium">
              {url}
            </span>
          </div>
        </div>
      </div>
      <div className="bg-black/80 h-full overflow-auto">
        <div className="flex flex-col gap-4 p-4">
          {images.map((imgSrc, index) => (
            <div key={index} className="flex flex-col gap-2">
              {imgSrc && (
                <img
                  src={imgSrc}
                  alt={`Image ${index + 1}`}
                  className="w-full object-contain max-h-[500px]"
                />
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default ImageBrowser;
