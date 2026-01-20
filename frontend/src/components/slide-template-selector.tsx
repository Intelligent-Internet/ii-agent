import { useState, useEffect } from 'react'
import { Button } from './ui/button'
import { Icon } from './ui/icon'
import { slideService, type SlideTemplate } from '@/services/slide.service'
import { toast } from 'sonner'

interface SlideTemplateSelectorProps {
    isVisible: boolean
    onTemplateSelect: (template: SlideTemplate) => void
    onClose: () => void
}

export const SlideTemplateSelector = ({
    isVisible,
    onTemplateSelect,
    onClose
}: SlideTemplateSelectorProps) => {
    const [templates, setTemplates] = useState<SlideTemplate[]>([])
    const [loading, setLoading] = useState(false)
    const [searchQuery, setSearchQuery] = useState('')
    const [selectedTemplate, setSelectedTemplate] =
        useState<SlideTemplate | null>(null)

    useEffect(() => {
        if (isVisible) {
            fetchTemplates()
        }
    }, [isVisible, searchQuery])

    const fetchTemplates = async () => {
        try {
            setLoading(true)
            console.log('[SlideTemplateSelector] Fetching templates...')
            const response = await slideService.getSlideTemplates(
                1,
                50, // Get more templates for better selection
                searchQuery || undefined
            )
            console.log('[SlideTemplateSelector] Response:', response)
            console.log('[SlideTemplateSelector] Templates:', response.templates)
            setTemplates(response.templates)
            // Auto-select the first template if none is selected
            if (response.templates.length > 0 && !selectedTemplate) {
                setSelectedTemplate(response.templates[0])
            }
        } catch (error) {
            console.error('[SlideTemplateSelector] Failed to fetch slide templates:', error)
            toast.error('Failed to load slide templates')
        } finally {
            setLoading(false)
        }
    }

    const handleTemplateClick = (template: SlideTemplate) => {
        // Set as selected template for preview
        setSelectedTemplate(template)
    }

    const handleGenerateSlides = () => {
        // Use the selected template
        if (selectedTemplate) {
            onTemplateSelect(selectedTemplate)
        } else {
            handleSkipTemplate()
        }
    }

    const handleSkipTemplate = () => {
        // Call onTemplateSelect with null to indicate no template selected
        onTemplateSelect(null as any)
    }

    if (!isVisible) return null

    return (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
            <div className="bg-grey-3/90 dark:bg-black/90 backdrop-blur-md rounded-xl border border-sky-blue w-[95vw] max-w-7xl h-[90vh] animate-fadeIn flex flex-col shadow-2xl pointer-events-auto">
                {/* Header */}
                <div className="p-3 md:p-6 border-b border-sky-blue flex-shrink-0">
                    <div className="flex items-center justify-between">
                        <h2 className="text-xl font-semibold text-black dark:text-white">
                            Choose Template
                        </h2>
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={onClose}
                            className="h-8 w-8 text-black/60 dark:text-white/60 hover:text-black dark:hover:text-white"
                        >
                            <Icon
                                name="cancel-2"
                                className="h-4 w-4 stroke-black dark:stroke-white"
                            />
                        </Button>
                    </div>
                </div>

                {/* Main Content - Split Layout */}
                <div className="flex flex-col md:flex-row flex-1 overflow-hidden">
                    {/* Left Side - Template List */}
                    <div className="w-full md:w-1/3 border-b md:border-r border-sky-blue flex flex-col">
                        {/* Search */}
                        <div className="p-4 border-b border-sky-blue">
                            <div className="relative">
                                <Icon
                                    name="search-2"
                                    className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-black/50 dark:text-white/50"
                                />
                                <input
                                    type="text"
                                    placeholder="Search templates..."
                                    value={searchQuery}
                                    onChange={(e) =>
                                        setSearchQuery(e.target.value)
                                    }
                                    className="w-full pl-10 pr-4 py-2 text-sm border border-grey rounded-lg bg-white dark:bg-neutral-900 text-black dark:text-white placeholder-black/50 dark:placeholder-white/50 focus:border-blue-500 focus:outline-none"
                                />
                            </div>
                        </div>

                        {/* Template Grid */}
                        <div className="flex-1 p-4 overflow-y-auto">
                            {loading ? (
                                <div className="flex items-center justify-center py-16">
                                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                                    <span className="ml-3 text-black/60 dark:text-white/60">
                                        Loading...
                                    </span>
                                </div>
                            ) : templates.length === 0 ? (
                                <div className="text-center py-16">
                                    <Icon
                                        name="note-2"
                                        className="h-12 w-12 text-black/40 dark:text-white/40 mx-auto mb-4"
                                    />
                                    <p className="text-black/60 dark:text-white/60">
                                        {searchQuery
                                            ? 'No templates found.'
                                            : 'No templates available.'}
                                    </p>
                                </div>
                            ) : (
                                <div className="grid grid-cols-2 gap-3 max-h-[200px] md:max-h-dvh overflow-auto">
                                    {templates.map((template) => (
                                        <div
                                            key={template.id}
                                            onClick={() =>
                                                handleTemplateClick(template)
                                            }
                                            className={`group cursor-pointer border rounded-lg overflow-hidden transition-all duration-200 hover:shadow-lg ${
                                                selectedTemplate?.id ===
                                                template.id
                                                    ? 'border-sky-blue ring-2 ring-sky-blue/50'
                                                    : 'border-grey hover:border-sky-blue'
                                            }`}
                                        >
                                            {/* Template Preview */}
                                            <div className="aspect-video bg-neutral-100 dark:bg-neutral-800 relative overflow-hidden">
                                                {template.slide_template_images &&
                                                template.slide_template_images
                                                    .length > 0 ? (
                                                    <iframe
                                                        src={
                                                            template
                                                                .slide_template_images[0]
                                                        }
                                                        title={
                                                            template.slide_template_name
                                                        }
                                                        className="border-0 pointer-events-none"
                                                        style={{
                                                            display: 'block',
                                                            width: '1280px',
                                                            height: '720px',
                                                            transform:
                                                                'scale(0.15)',
                                                            transformOrigin:
                                                                'top left',
                                                            position:
                                                                'absolute',
                                                            top: 0,
                                                            left: 0
                                                        }}
                                                        scrolling="no"
                                                        loading="lazy"
                                                    />
                                                ) : (
                                                    <div className="flex flex-col items-center justify-center h-full text-black/40 dark:text-white/40">
                                                        <Icon
                                                            name="slide"
                                                            className="h-6 w-6 mb-1"
                                                        />
                                                        <span className="text-xs">
                                                            No Preview
                                                        </span>
                                                    </div>
                                                )}
                                            </div>
                                            {/* Template Name */}
                                            <div className="p-2 bg-white dark:bg-neutral-900 border-t border-grey">
                                                <p className="text-sm font-medium text-black dark:text-white truncate">
                                                    {template.slide_template_name}
                                                </p>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Right Side - Large Preview */}
                    <div className="flex-1 flex flex-col">
                        {selectedTemplate ? (
                            <>
                                {/* Large Preview */}
                                <div className="flex-1 md:p-6 flex flex-col">
                                    {selectedTemplate.slide_template_images &&
                                    selectedTemplate.slide_template_images
                                        .length > 0 ? (
                                        <div className="flex flex-col gap-3 h-full p-4">
                                            {/* Main large preview */}
                                            <div className="flex items-center justify-center">
                                                <div className="w-full max-w-3xl aspect-video bg-neutral-100 dark:bg-neutral-800 rounded-lg overflow-hidden shadow-2xl relative">
                                                    <iframe
                                                        src={
                                                            selectedTemplate
                                                                .slide_template_images[0]
                                                        }
                                                        title={`${selectedTemplate.slide_template_name} - Main Preview`}
                                                        className="border-0"
                                                        style={{
                                                            display: 'block',
                                                            width: '1280px',
                                                            height: '720px',
                                                            transform:
                                                                'scale(0.6)',
                                                            transformOrigin:
                                                                'left top 0px'
                                                        }}
                                                        scrolling="no"
                                                        loading="lazy"
                                                    />
                                                </div>
                                            </div>

                                            {/* Additional images grid below */}
                                            {selectedTemplate
                                                .slide_template_images.length >
                                                1 && (
                                                <div className="w-full max-w-3xl mx-auto">
                                                    <div className="grid grid-cols-3 gap-2">
                                                        {selectedTemplate.slide_template_images
                                                            .slice(1, 4)
                                                            .map(
                                                                (
                                                                    image,
                                                                    index
                                                                ) => (
                                                                    <div
                                                                        key={
                                                                            index
                                                                        }
                                                                        className="aspect-video bg-neutral-100 dark:bg-neutral-800 rounded-md overflow-hidden shadow-md relative"
                                                                    >
                                                                        <iframe
                                                                            src={
                                                                                image
                                                                            }
                                                                            title={`${selectedTemplate.slide_template_name} - Preview ${index + 2}`}
                                                                            className="border-0"
                                                                            style={{
                                                                                display:
                                                                                    'block',
                                                                                width: '1280px',
                                                                                height: '720px',
                                                                                transform:
                                                                                    'scale(0.2)',
                                                                                transformOrigin:
                                                                                    'left top 0px'
                                                                            }}
                                                                            scrolling="no"
                                                                            loading="lazy"
                                                                        />
                                                                    </div>
                                                                )
                                                            )}
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    ) : (
                                        <div className="flex-1 flex items-center justify-center">
                                            <div className="flex flex-col items-center justify-center text-black/40 dark:text-white/40">
                                                <Icon
                                                    name="slide"
                                                    className="h-24 w-24 mb-4"
                                                />
                                                <span className="text-lg">
                                                    No Preview Available
                                                </span>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </>
                        ) : (
                            <div className="flex-1 flex items-center justify-center">
                                <div className="text-center text-black/40 dark:text-white/40">
                                    <Icon
                                        name="slide"
                                        className="h-16 w-16 mx-auto mb-4"
                                    />
                                    <p className="text-lg">
                                        Select a template to preview
                                    </p>
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                {/* Footer */}
                <div className="px-3 md:px-6 py-4 border-t border-sky-blue flex items-center justify-between flex-shrink-0">
                    <div className="flex items-center md:gap-2">
                        <Button
                            variant="ghost"
                            onClick={onClose}
                            className="px-3 pr-2 md:px-4 text-black/60 dark:text-white/60 hover:text-black dark:hover:text-white"
                        >
                            Cancel
                        </Button>
                        <Button
                            variant="ghost"
                            onClick={handleSkipTemplate}
                            className="px-3 md:px-4 text-black/60 dark:text-white/60 hover:text-black dark:hover:text-white"
                        >
                            Skip Template
                        </Button>
                    </div>
                    <Button
                        onClick={handleGenerateSlides}
                        className="bg-firefly dark:bg-sky-blue hover:bg-firefly/90 dark:hover:bg-sky-blue/90 text-black"
                    >
                        <Icon name="slide-2" className="h-4 w-4 stroke-black" />
                        Generate Slides
                    </Button>
                </div>
            </div>
        </div>
    )
}
