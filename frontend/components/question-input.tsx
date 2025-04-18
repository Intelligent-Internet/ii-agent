import { motion } from "framer-motion";
import { ArrowUp } from "lucide-react";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";

interface QuestionInputProps {
  className?: string;
  textareaClassName?: string;
  placeholder?: string;
  value: string;
  setValue: (value: string) => void;
  handleKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  handleSubmit: (question: string) => void;
}

const QuestionInput = ({
  className,
  textareaClassName,
  placeholder,
  value,
  setValue,
  handleKeyDown,
  handleSubmit,
}: QuestionInputProps) => {
  return (
    <motion.div
      key="input-view"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95, y: -10 }}
      transition={{
        type: "spring",
        stiffness: 300,
        damping: 30,
        mass: 1,
      }}
      className={`w-full max-w-2xl shadow-[0_2px_6px_rgba(0,0,0,0.07)] dark:shadow-[0_2px_6px_rgba(255,255,255,0.07)] z-50 ${className}`}
    >
      <motion.div
        className="relative rounded-xl bg-white/50 dark:bg-slate-800/50"
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.1 }}
      >
        <Textarea
          className={`w-full h-40 p-4 rounded-lg !text-lg bg-transparent border-none focus:ring-0 focus:border-none resize-none ${textareaClassName}`}
          placeholder={
            placeholder ||
            "Enter your research query or complex question for in-depth analysis..."
          }
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <div className="flex w-full justify-between items-center absolute bottom-4 px-4">
          <div />
          <Button
            disabled={!value.trim()}
            onClick={() => handleSubmit(value)}
            className="cursor-pointer p-4 size-10 font-bold bg-gradient-skyblue-lavender rounded-full hover:scale-105 active:scale-95 transition-transform shadow-[0_4px_10px_rgba(0,0,0,0.1)] dark:shadow-[0_4px_10px_rgba(0,0,0,0.2)]"
          >
            <ArrowUp className="size-5" />
          </Button>
        </div>
      </motion.div>
    </motion.div>
  );
};

export default QuestionInput;
