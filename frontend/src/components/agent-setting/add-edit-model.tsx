import { useState, useEffect } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import dayjs from 'dayjs'
import { Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Icon } from '../ui/icon'
import { Sheet, SheetClose, SheetContent, SheetHeader } from '../ui/sheet'
import { PROVIDER, PROVIDER_MODELS, PROVIDERS_NAME, getProviderKey } from '@/constants/models'
import { ProviderType } from '@/typings/settings'

/** Map FE UI key to BE Provider enum value. */
const UI_KEY_TO_PROVIDER: Record<string, ProviderType> = {
    anthropic: PROVIDER.ANTHROPIC,
    openai: PROVIDER.OPENAI,
    gemini: PROVIDER.GOOGLE,
    cerebras: PROVIDER.CEREBRAS,
    atlascloud: PROVIDER.ATLASCLOUD,
    custom: PROVIDER.CUSTOM,
}
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue
} from '../ui/select'
import { Input } from '../ui/input'
import { Button } from '../ui/button'
import {
    Form,
    FormControl,
    FormField,
    FormItem,
    FormLabel,
    FormMessage
} from '../ui/form'
import { IModel } from '@/typings/settings'
import { settingsService } from '@/services/settings.service'
import { useAppSelector } from '@/state/store'

interface AddEditModelProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    onSaveConfig: (model: IModel, isEdit: boolean) => Promise<void>
    editingModel?: IModel | null
}

const FormSchema = z.object({
    model: z
        .custom<IModel>()
        .optional(),
    custom_model_name: z.string().optional(),
    api_key: z.string().optional(),
    azure_endpoint: z.string().optional(),
    azure_api_version: z.string().optional(),
    vertex_region: z.string().optional(),
    vertex_project_id: z.string().optional(),
    base_url: z.string().optional()
})

const AddEditModel = ({
    open,
    onOpenChange,
    onSaveConfig,
    editingModel
}: AddEditModelProps) => {
    const { t } = useTranslation()
    const isEditing = !!editingModel
    const [selectedProvider, setSelectedProvider] = useState('anthropic')
    const [isSaving, setIsSaving] = useState(false)
    const [editModelData, setEditModelData] = useState<IModel>()

    const currentSettingData = useAppSelector(
        (state) => state.settings.currentSettingData
    )

    const form = useForm<z.infer<typeof FormSchema>>({
        resolver: zodResolver(FormSchema),
        defaultValues: {
            model: PROVIDER_MODELS.anthropic[0]
        }
    })

    const selectedModel = useWatch({ control: form.control, name: 'model' })

    const handleProviderChange = (provider: string) => {
        setSelectedProvider(provider)
        form.setValue(
            'model',
            PROVIDER_MODELS[provider as keyof typeof PROVIDER_MODELS][0]
        )
        form.setValue('custom_model_name', '')
    }

    const onSubmit = async (data: z.infer<typeof FormSchema>) => {
        const model = data.model as IModel
        const customName = data.custom_model_name || ''

        // Create model object
        const modelData: IModel = {
            id: isEditing && editingModel ? editingModel?.id : '',
            model:
                model?.model === 'custom' ||
                selectedProvider === 'custom' ||
                selectedProvider === 'atlascloud'
                    ? customName
                    : model.model,
            provider: UI_KEY_TO_PROVIDER[selectedProvider] ?? PROVIDER.CUSTOM,
            source: 'user'
        }

        const additionalConfig: {
            api_key?: string
            base_url?: string
        } = {}

        if (selectedProvider === 'anthropic' && data.api_key) {
            additionalConfig.api_key = data.api_key
        } else if (
            selectedProvider === 'openai' ||
            selectedProvider === 'custom' ||
            selectedProvider === 'atlascloud'
        ) {
            if (data.api_key) additionalConfig.api_key = data.api_key
            if (data.base_url) additionalConfig.base_url = data.base_url
        } else if (selectedProvider === 'gemini' && data.api_key) {
            additionalConfig.api_key = data.api_key
        }

        const finalModelData = { ...modelData, ...additionalConfig }

        try {
            setIsSaving(true)
            if (editingModel) {
                const res = await settingsService.updateModel(
                    editingModel?.id,
                    finalModelData
                )
                await onSaveConfig(res, isEditing)
            } else {
                const res = await settingsService.createModel(finalModelData)
                await onSaveConfig(res, false)
            }
            onOpenChange(false)
        } catch (error) {
            console.error('Error saving model:', error)
        } finally {
            setIsSaving(false)
        }
    }

    useEffect(() => {
        if (editingModel) {
            ;(async () => {
                const config = await settingsService.getModelById(
                    editingModel?.id
                )
                const providerKey = getProviderKey(config)
                setSelectedProvider(providerKey)
                setEditModelData(config)
                let modelObj: IModel | undefined =
                    PROVIDER_MODELS[
                        providerKey as keyof typeof PROVIDER_MODELS
                    ]?.find((m) => m.model === config?.model)
                if (!modelObj) {
                    modelObj = {
                        id: '',
                        model: 'custom',
                        provider: UI_KEY_TO_PROVIDER[providerKey] ?? PROVIDER.CUSTOM
                    }
                    form.setValue('custom_model_name', config.model)
                }
                if (config.api_key === 'custom') {
                    form.setValue('custom_model_name', config.model)
                }
                form.setValue('model', modelObj)
                form.setValue('api_key', config.api_key || '')
                form.setValue('base_url', config.base_url || '')
            })()
        } else {
            setSelectedProvider('anthropic')
            form.reset({
                model: PROVIDER_MODELS.anthropic[0]
            })
        }
    }, [isEditing, editingModel, currentSettingData, form])

    return (
        <Sheet open={open} onOpenChange={onOpenChange}>
            <SheetContent className="pt-3 md:pt-12 w-full !max-w-[480px]">
                <SheetHeader className="px-3 md:px-6 pt-0 gap-1 pb-4">
                    <div className="flex items-center justify-between">
                        <p className="text-2xl font-semibold">
                            {isEditing
                                ? t('agentSetting.addEditModel.title.edit')
                                : t('agentSetting.addEditModel.title.add')}
                        </p>
                        <div className="flex items-center gap-x-4">
                            <SheetClose className="cursor-pointer">
                                <Icon
                                    name="arrow-right"
                                    className="dark:inline hidden"
                                />
                                <Icon
                                    name="arrow-right-dark"
                                    className="dark:hidden inline"
                                />
                            </SheetClose>
                        </div>
                    </div>
                    <p className="text-sm text-black/[0.56] dark:text-white/[0.56]">
                        {t('agentSetting.addEditModel.description')}
                    </p>
                </SheetHeader>
                <Form {...form}>
                    <form
                        onSubmit={form.handleSubmit(onSubmit)}
                        className="space-y-6 px-3 md:px-6 overflow-auto pb-4 md:pb-12"
                    >
                        <div className="space-y-4">
                            <p className="text-lg font-semibold dark:text-white">
                                {t('agentSetting.addEditModel.sections.provider')}
                            </p>
                            <div className="grid grid-cols-3 gap-4">
                                {[
                                    'anthropic',
                                    'openai',
                                    'gemini',
                                    'atlascloud',
                                    'custom'
                                ].map((provider) => (
                                    <div
                                        key={provider}
                                        className={`h-[120px] flex items-center flex-col gap-4 rounded-2xl cursor-pointer ${
                                            selectedProvider === provider
                                                ? 'border-2 border-firefly dark:border-sky-blue-2 bg-sky-blue dark:bg-sky-blue-2/20 p-[14px] font-semibold'
                                                : 'bg-firefly/5 dark:bg-sky-blue-2/5 p-4'
                                        }`}
                                        onClick={() => {
                                            handleProviderChange(provider)
                                        }}
                                    >
                                        <img
                                            src={`/images/${provider}.svg`}
                                            alt={provider}
                                            className={`w-auto h-[53px] ${
                                                provider === 'anthropic' ||
                                                provider === 'openai'
                                                    ? 'hidden dark:inline'
                                                    : ''
                                            }`}
                                        />
                                        {(provider === 'anthropic' ||
                                            provider === 'openai') && (
                                            <img
                                                src={`/images/${provider}-dark.svg`}
                                                alt={provider}
                                                className="w-auto h-[53px] inline dark:hidden"
                                            />
                                        )}
                                        <p className="text-sm dark:text-white">
                                            {PROVIDERS_NAME[provider]}
                                        </p>
                                    </div>
                                ))}
                            </div>
                        </div>
                        {selectedProvider !== 'custom' &&
                            selectedProvider !== 'atlascloud' && (
                            <FormField
                                control={form.control}
                                name="model"
                                render={({ field }) => (
                                    <FormItem>
                                        <FormLabel className="text-lg">
                                            {t(
                                                'agentSetting.addEditModel.fields.modelName'
                                            )}
                                        </FormLabel>
                                        <FormControl>
                                            <Select
                                                onValueChange={(value) => {
                                                    const model =
                                                        PROVIDER_MODELS[
                                                            selectedProvider as keyof typeof PROVIDER_MODELS
                                                        ].find(
                                                            (m) =>
                                                                m.model ===
                                                                value
                                                        )
                                                    if (model) {
                                                        field.onChange(model)
                                                    }
                                                }}
                                                value={field.value?.model}
                                            >
                                                <SelectTrigger className="w-full **:fill-black **:dark:fill-white">
                                                    <div className="flex items-center gap-4">
                                                        <SelectValue
                                                            placeholder={t(
                                                                'agentSetting.addEditModel.fields.selectModel'
                                                            )}
                                                        />
                                                    </div>
                                                </SelectTrigger>
                                                <SelectContent>
                                                    {PROVIDER_MODELS[
                                                        selectedProvider as keyof typeof PROVIDER_MODELS
                                                    ].map((model) => (
                                                        <SelectItem
                                                            key={model.model}
                                                            value={model.model}
                                                        >
                                                            <div className="flex items-center gap-4">
                                                                <Icon
                                                                    name="cpu"
                                                                    className={`size-6 fill-black`}
                                                                />
                                                                {model.model}
                                                            </div>
                                                        </SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                        </FormControl>
                                    </FormItem>
                                )}
                            />
                        )}
                        <div className="space-y-4">
                            {(selectedModel?.model === 'custom' ||
                                selectedProvider === 'custom' ||
                                selectedProvider === 'atlascloud') && (
                                <FormField
                                    control={form.control}
                                    name="custom_model_name"
                                    render={({ field }) => (
                                        <FormItem>
                                            {(selectedProvider === 'custom' ||
                                                selectedProvider ===
                                                    'atlascloud') && (
                                                <FormLabel className="text-lg">
                                                    {t(
                                                        'agentSetting.addEditModel.fields.modelName'
                                                    )}
                                                </FormLabel>
                                            )}
                                            <FormControl>
                                                <div className="space-y-2 relative">
                                                    <Icon
                                                        name="cpu"
                                                        className="absolute top-3 left-4 fill-white"
                                                    />
                                                    <Input
                                                        id="custom-model-name"
                                                        className="pl-[56px]"
                                                        type="text"
                                                        placeholder={t(
                                                            'agentSetting.addEditModel.fields.customModelPlaceholder'
                                                        )}
                                                        {...field}
                                                    />
                                                </div>
                                            </FormControl>
                                        </FormItem>
                                    )}
                                />
                            )}
                        </div>
                        {selectedProvider === 'anthropic' && (
                            <FormField
                                control={form.control}
                                name="api_key"
                                render={({ field }) => (
                                    <FormItem>
                                        <FormLabel className="text-lg">
                                            {t(
                                                'agentSetting.addEditModel.fields.apiKeyLabel'
                                            )}
                                        </FormLabel>
                                        <FormControl>
                                            <div className="space-y-2 relative">
                                                <Icon
                                                    name="key-square"
                                                    className={`absolute top-3 left-4 fill-black dark:fill-white ${field.value ? '' : 'opacity-30'}`}
                                                />
                                                <Input
                                                    id="api-key"
                                                    className="pl-[56px]"
                                                    type="password"
                                                    placeholder={t(
                                                        'agentSetting.addEditModel.fields.apiKeyPlaceholder'
                                                    )}
                                                    {...field}
                                                />
                                            </div>
                                        </FormControl>
                                        {isEditing && (
                                            <FormMessage className="mt-1 pl-4">
                                                <div className="flex gap-x-2 items-center">
                                                    <span className="font-semibold text-sm italic">
                                                        {t(
                                                            'agentSetting.addEditModel.fields.latestUpdate'
                                                        )}
                                                    </span>
                                                    <span>
                                                        {dayjs().format(
                                                            'DD/MM/YYYY -- HH:mm:ss'
                                                        )}
                                                    </span>
                                                </div>
                                            </FormMessage>
                                        )}
                                    </FormItem>
                                )}
                            />
                        )}
                        {(selectedProvider === 'openai' ||
                            selectedProvider === 'custom' ||
                            selectedProvider === 'atlascloud') && (
                            <>
                                <FormField
                                    control={form.control}
                                    name="api_key"
                                    render={({ field }) => (
                                    <FormItem>
                                        <FormLabel className="text-lg">
                                            {t(
                                                'agentSetting.addEditModel.fields.apiKeyLabel'
                                            )}
                                        </FormLabel>
                                        <FormControl>
                                            <div className="space-y-2 relative">
                                                    <Icon
                                                        name="key-square"
                                                        className={`absolute top-3 left-4 fill-black dark:fill-white ${field.value ? '' : 'opacity-30'}`}
                                                    />
                                                <Input
                                                    id="api-key"
                                                    className="pl-[56px]"
                                                    type="password"
                                                    placeholder={t(
                                                        'agentSetting.addEditModel.fields.apiKeyPlaceholder'
                                                    )}
                                                    {...field}
                                                />
                                                </div>
                                            </FormControl>
                                            {isEditing && (
                                                <FormMessage className="mt-1 pl-4">
                                                <div className="flex gap-x-2 items-center">
                                                    <span className="font-semibold text-sm italic">
                                                        {t(
                                                            'agentSetting.addEditModel.fields.latestUpdate'
                                                        )}
                                                    </span>
                                                        <span>
                                                            {dayjs().format(
                                                                'DD/MM/YYYY -- HH:mm:ss'
                                                            )}
                                                        </span>
                                                    </div>
                                                </FormMessage>
                                            )}
                                        </FormItem>
                                    )}
                                />
                                <FormField
                                    control={form.control}
                                    name="base_url"
                                    render={({ field }) => (
                                        <FormItem>
                                        <FormLabel className="text-lg">
                                            {selectedProvider === 'custom' ||
                                            selectedProvider === 'atlascloud'
                                                ? t(
                                                      'agentSetting.addEditModel.fields.baseUrlLabel'
                                                  )
                                                : t(
                                                      'agentSetting.addEditModel.fields.baseUrlOptionalLabel'
                                                  )}
                                        </FormLabel>
                                            <FormControl>
                                                <div className="space-y-2 relative">
                                                    <Icon
                                                        name="link-2"
                                                        className={`absolute top-3 left-4 fill-black dark:fill-white ${field.value ? '' : 'opacity-30'}`}
                                                    />
                                                    <Input
                                                        id="base-url"
                                                        className="pl-[56px]"
                                                        type="text"
                                                        placeholder={t(
                                                            'agentSetting.addEditModel.fields.baseUrlPlaceholder'
                                                        )}
                                                        {...field}
                                                    />
                                                </div>
                                            </FormControl>
                                        </FormItem>
                                    )}
                                />
                            </>
                        )}
                        {selectedProvider === 'gemini' && (
                            <FormField
                                control={form.control}
                                name="api_key"
                                render={({ field }) => (
                                    <FormItem>
                                        <FormLabel className="text-lg">
                                            {t(
                                                'agentSetting.addEditModel.fields.apiKeyLabel'
                                            )}
                                        </FormLabel>
                                        <FormControl>
                                            <div className="space-y-2 relative">
                                                <Icon
                                                    name="key-square"
                                                    className={`absolute top-3 left-4 fill-black dark:fill-white ${field.value ? '' : 'opacity-30'}`}
                                                />
                                                <Input
                                                    id="api-key"
                                                    className="pl-[56px]"
                                                    type="password"
                                                    placeholder={t(
                                                        'agentSetting.addEditModel.fields.apiKeyPlaceholder'
                                                    )}
                                                    {...field}
                                                />
                                            </div>
                                        </FormControl>
                                        {isEditing && (
                                            <FormMessage className="mt-1 pl-4">
                                                <div className="flex gap-x-2 items-center">
                                                    <span className="font-semibold text-sm italic">
                                                        {t(
                                                            'agentSetting.addEditModel.fields.latestUpdate'
                                                        )}
                                                    </span>
                                                    <span>
                                                        {dayjs().format(
                                                            'DD/MM/YYYY -- HH:mm:ss'
                                                        )}
                                                    </span>
                                                </div>
                                            </FormMessage>
                                        )}
                                    </FormItem>
                                )}
                            />
                        )}
                        {selectedProvider === 'vertex' && (
                            <>
                                <FormField
                                    control={form.control}
                                    name="vertex_project_id"
                                    render={({ field }) => (
                                        <FormItem>
                                        <FormLabel className="text-lg">
                                            {t(
                                                'agentSetting.addEditModel.fields.vertexProjectIdLabel'
                                            )}
                                        </FormLabel>
                                            <FormControl>
                                                <div className="space-y-2 relative">
                                                    <Icon
                                                        name="folder-2"
                                                        className={`absolute top-3 left-4 fill-black dark:fill-white ${field.value ? '' : 'opacity-30'}`}
                                                    />
                                                    <Input
                                                        id="vertex-project-id"
                                                        className="pl-[56px]"
                                                        type="text"
                                                        placeholder={t(
                                                            'agentSetting.addEditModel.fields.vertexProjectIdPlaceholder'
                                                        )}
                                                        {...field}
                                                    />
                                                </div>
                                            </FormControl>
                                        </FormItem>
                                    )}
                                />
                                <FormField
                                    control={form.control}
                                    name="vertex_region"
                                    render={({ field }) => (
                                        <FormItem>
                                        <FormLabel className="text-lg">
                                            {t(
                                                'agentSetting.addEditModel.fields.vertexRegionLabel'
                                            )}
                                        </FormLabel>
                                            <FormControl>
                                                <div className="space-y-2 relative">
                                                    <Icon
                                                        name="global"
                                                        className={`absolute top-3 left-4 fill-black dark:fill-white ${field.value ? '' : 'opacity-30'}`}
                                                    />
                                                    <Input
                                                        id="vertex-region"
                                                        className="pl-[56px]"
                                                        type="text"
                                                        placeholder={t(
                                                            'agentSetting.addEditModel.fields.vertexRegionPlaceholder'
                                                        )}
                                                        {...field}
                                                    />
                                                </div>
                                            </FormControl>
                                        </FormItem>
                                    )}
                                />
                            </>
                        )}

                        {selectedProvider === 'azure' && (
                            <>
                                <FormField
                                    control={form.control}
                                    name="azure_endpoint"
                                    render={({ field }) => (
                                        <FormItem>
                                        <FormLabel className="text-lg">
                                            {t(
                                                'agentSetting.addEditModel.fields.azureEndpointLabel'
                                            )}
                                        </FormLabel>
                                            <FormControl>
                                                <div className="space-y-2 relative">
                                                    <Icon
                                                        name="cd"
                                                        className={`absolute top-3 left-4 fill-black dark:fill-white ${field.value ? '' : 'opacity-30'}`}
                                                    />
                                                    <Input
                                                        id="azure-endpoint"
                                                        className="pl-[56px]"
                                                        type="text"
                                                        placeholder={t(
                                                            'agentSetting.addEditModel.fields.azureEndpointPlaceholder'
                                                        )}
                                                        {...field}
                                                    />
                                                </div>
                                            </FormControl>
                                        </FormItem>
                                    )}
                                />
                                <FormField
                                    control={form.control}
                                    name="api_key"
                                    render={({ field }) => (
                                    <FormItem>
                                        <FormLabel className="text-lg">
                                            {t(
                                                'agentSetting.addEditModel.fields.apiKeyLabel'
                                            )}
                                        </FormLabel>
                                        <FormControl>
                                            <div className="space-y-2 relative">
                                                    <Icon
                                                        name="key-square"
                                                        className={`absolute top-3 left-4 fill-black dark:fill-white ${field.value ? '' : 'opacity-30'}`}
                                                    />
                                                <Input
                                                    id="api-key"
                                                    className="pl-[56px]"
                                                    type="password"
                                                    placeholder={t(
                                                        'agentSetting.addEditModel.fields.apiKeyPlaceholder'
                                                    )}
                                                    {...field}
                                                />
                                                </div>
                                            </FormControl>
                                            {isEditing && (
                                                <FormMessage className="mt-1 pl-4">
                                                <div className="flex gap-x-2 items-center">
                                                    <span className="font-semibold text-sm italic">
                                                        {t(
                                                            'agentSetting.addEditModel.fields.latestUpdate'
                                                        )}
                                                    </span>
                                                        <span>
                                                            {dayjs(
                                                                editModelData?.updated_at
                                                            ).format(
                                                                'DD/MM/YYYY -- HH:mm:ss'
                                                            )}
                                                        </span>
                                                    </div>
                                                </FormMessage>
                                            )}
                                        </FormItem>
                                    )}
                                />
                                <FormField
                                    control={form.control}
                                    name="azure_api_version"
                                    render={({ field }) => (
                                        <FormItem>
                                        <FormLabel className="text-lg">
                                            {t(
                                                'agentSetting.addEditModel.fields.azureApiVersionLabel'
                                            )}
                                        </FormLabel>
                                            <FormControl>
                                                <div className="space-y-2 relative">
                                                    <Icon
                                                        name="tag-2"
                                                        className={`absolute top-3 left-4 fill-black dark:fill-white ${field.value ? '' : 'opacity-30'}`}
                                                    />
                                                    <Input
                                                        id="azure-api-version"
                                                        className="pl-[56px]"
                                                        type="text"
                                                        placeholder={t(
                                                            'agentSetting.addEditModel.fields.azureApiVersionPlaceholder'
                                                        )}
                                                        {...field}
                                                    />
                                                </div>
                                            </FormControl>
                                        </FormItem>
                                    )}
                                />
                            </>
                        )}
                        <div className="grid grid-cols-2 gap-4 mt-12">
                            <Button
                                type="reset"
                                variant="outline"
                                className="col-span-1 h-12 rounded-xl text-base"
                                onClick={() => onOpenChange(false)}
                            >
                                {t('common.cancel')}
                            </Button>
                            <Button
                                type="submit"
                                className="col-span-1 h-12 rounded-xl bg-firefly dark:bg-sky-blue text-sky-blue-2 dark:text-black text-base"
                                disabled={isSaving}
                            >
                                {isSaving && (
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                )}
                                {t('common.save')}
                            </Button>
                        </div>
                    </form>
                </Form>
            </SheetContent>
        </Sheet>
    )
}

export default AddEditModel
