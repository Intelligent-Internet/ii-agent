import { motion } from "framer-motion";
import { ArrowUp } from "lucide-react";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";

interface QuestionInputProps {
  question: string;
  placeholder?: string;
  setQuestion: (question: string) => void;
  handleKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  handleSubmit: () => void;
}

const QuestionInput = ({
  question,
  placeholder,
  setQuestion,
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
      className="w-full max-w-2xl"
    >
      <motion.div
        className="bg-white rounded-2xl shadow-lg relative mt-6"
        initial={{ boxShadow: "0 4px 6px rgba(0, 0, 0, 0.1)" }}
        animate={{ boxShadow: "0 10px 25px rgba(0, 0, 0, 0.1)" }}
        transition={{ delay: 0.2, duration: 0.5 }}
      >
        <Textarea
          className="w-full h-40 p-4 rounded-lg !text-lg"
          placeholder={
            placeholder ||
            "Enter your research query or complex question for in-depth analysis..."
          }
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <div className="flex w-full justify-between items-center absolute bottom-4 px-4">
          <div />
          <Button
            disabled={!question.trim()}
            onClick={handleSubmit}
            className="cursor-pointer p-4 size-10 font-bold  bg-gradient-skyblue-lavender rounded-full hover:scale-105 active:scale-95 transition-transform"
          >
            <ArrowUp className="size-5" />
          </Button>
        </div>
      </motion.div>
    </motion.div>
  );
};

export default QuestionInput;
