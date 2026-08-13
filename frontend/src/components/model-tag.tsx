import {
    selectAvailableModels,
    selectSelectedChatModel,
    selectSelectedAgentModel,
    selectQuestionMode,
    useAppSelector
} from '@/state'
import { QUESTION_MODE } from '@/typings'

const ModelTag = () => {
    const questionMode = useAppSelector(selectQuestionMode)
    const selectedChatModel = useAppSelector(selectSelectedChatModel)
    const selectedAgentModel = useAppSelector(selectSelectedAgentModel)
    const availableModels = useAppSelector(selectAvailableModels)

    const selectedModel = questionMode === QUESTION_MODE.CHAT
        ? selectedChatModel
        : selectedAgentModel

    const model = availableModels.find((m) => m.id === selectedModel)

    if (!selectedModel) return null

    return (
        <p className="model-tag bg-blue-gradient h-7 flex line-clamp-1 whitespace-pre justify-center items-center text-black text-[12px] font-bold px-4 rounded-[30px]">
            {model?.model}
        </p>
    )
}

export default ModelTag
