import { useState } from "react";
import { motion } from "framer-motion";
import { Loader2, Lightbulb } from "lucide-react";

import { AccordionContent } from "./ui/accordion";
import { AccordionItem, AccordionTrigger } from "./ui/accordion";
import { Accordion } from "./ui/accordion";
import ThinkingStep from "./thinking-step";
import { ThoughtStep } from "@/typings/agent";

interface ThoughtsProps {
  isStreamingThought: boolean;
  thoughtData: ThoughtStep[];
  sources: {
    [key: string]: {
      url: string;
      result: {
        content: string;
      };
    };
  };
}

const Thoughts = ({
  isStreamingThought,
  thoughtData,
  sources,
}: ThoughtsProps) => {
  const [isOpenThough, setIsOpenThough] = useState(true);

  return (
    <motion.div
      className={`mb-4 text-left`}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2, duration: 0.3 }}
    >
      <Accordion
        value={isOpenThough ? ["deep-research"] : []}
        type="multiple"
        className="px-4 bg-neutral-800 rounded-lg"
      >
        <AccordionItem value="deep-research">
          <AccordionTrigger
            className="text-lg font-medium hover:!no-underline cursor-pointer"
            onClick={() => setIsOpenThough((prev) => !prev)}
          >
            <span className="flex items-center gap-x-2">
              {isStreamingThought ? (
                <Loader2 className="animate-spin" />
              ) : (
                <Lightbulb />
              )}{" "}
              Thoughts
            </span>
          </AccordionTrigger>
          <AccordionContent className="space-y-3 max-h-[300px] thought-list overflow-y-auto">
            {thoughtData.map((thought, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{
                  delay: index * 0.1,
                  duration: 0.3,
                  ease: "easeOut",
                }}
              >
                <ThinkingStep value={thought} sources={sources} />
              </motion.div>
            ))}
            {isStreamingThought && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.5 }}
                className="mt-2"
              >
                <div className="h-3 bg-neutral-700 rounded w-full relative overflow-hidden">
                  <div
                    className="absolute inset-0 bg-neutral-600"
                    style={{
                      animation: "shimmer 2.5s infinite",
                      background:
                        "linear-gradient(to right, transparent, rgba(255,255,255,0.5), transparent)",
                      transform: "translateX(-100%)",
                    }}
                  />
                </div>
              </motion.div>
            )}
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </motion.div>
  );
};

export default Thoughts;
