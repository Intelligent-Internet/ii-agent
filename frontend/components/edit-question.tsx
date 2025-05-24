import { motion } from "framer-motion";
import { ArrowUp } from "lucide-react";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";
import { useEffect, useState } from "react";

interface EditQuestionProps {
  className?: string;
  textareaClassName?: string;
  editingMessage: string;
  handleCancel?: () => void;
  handleEditMessage: (newContent: string) => void;
}

const EditQuestion = ({
  className,
  textareaClassName,
  editingMessage,
  handleCancel,
  handleEditMessage,
}: EditQuestionProps) => {
  const [value, setValue] = useState("");

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleEditMessage(value);
    }
  };

  useEffect(() => {
    setValue(editingMessage);
  }, [editingMessage]);

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
      className={`w-full max-w-2xl z-50 ${className}`}
    >
      <motion.div
        className="relative rounded-xl"
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.1 }}
      >
        <Textarea
          className={`w-full p-0 pb-[72px] rounded-xl !text-lg focus-visible:ring-0 resize-none !placeholder-gray-400 !bg-[#35363a] border-none h-50 ${textareaClassName}`}
          placeholder={"Ask me anything..."}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <div className="flex justify-end items-center absolute bottom-0 m-px w-[calc(100%-4px)] rounded-b-xl bg-[#35363a]">
          <div className="flex items-center gap-x-2">
            <Button
              onClick={handleCancel}
              className="cursor-pointer h-10 bg-transparent text-white hover:bg-transparent border border-[#ffffff0f] hover:scale-105 active:scale-95 transition-transform"
            >
              Cancel
            </Button>

            <Button
              disabled={!value.trim()}
              onClick={() => handleEditMessage(value)}
              className="cursor-pointer !border !border-red p-4 size-10 font-bold bg-gradient-skyblue-lavender rounded-full hover:scale-105 active:scale-95 transition-transform shadow-[0_4px_10px_rgba(0,0,0,0.2)]"
            >
              <ArrowUp className="size-5" />
            </Button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
};

export default EditQuestion;
