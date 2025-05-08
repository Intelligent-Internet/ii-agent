() => {

    console.time('totalExecutionTime');

    // Define element weights for interactive likelihood - moved to higher scope
    const elementWeights = {
        'button': 10,
        'a': 10,
        'input': 10,
        'select': 10,
        'textarea': 10,
        'summary': 8,
        'details': 7,
        'label': 5, // Labels are clickable but not always interactive
        'option': 7,
        'tr': 4,
        'th': 3,
        'td': 3,
        'li': 8,
        'div': 2,
        'span': 1,
        'img': 2,
        'svg': 3,
        'path': 3
    };

    function generateUniqueId() {
        const rand = Math.random().toString(36);
        return `ba-${rand}`;
    } 

    // Add this helper function to check element coverage
    function isElementTooBig(rect) {
        const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
        const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
        const viewportArea = viewportWidth * viewportHeight;

        // Calculate visible area of the element
        const visibleWidth = Math.min(rect.right, viewportWidth) - Math.max(rect.left, 0);
        const visibleHeight = Math.min(rect.bottom, viewportHeight) - Math.max(rect.top, 0);
        const visibleArea = visibleWidth * visibleHeight;

        // Check if element covers more than 50% of viewport
        return (visibleArea / viewportArea) > 0.5;
    }

    // Helper function to check if element is in the visible viewport
    function isInViewport(rect) {
        // Get viewport dimensions
        const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
        const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
        
        // Element must have meaningful size
        if (rect.width < 2 || rect.height < 2) {
            return false;
        }
        
        // Check if substantial part of the element is in viewport (at least 30%)
        const visibleWidth = Math.min(rect.right, viewportWidth) - Math.max(rect.left, 0);
        const visibleHeight = Math.min(rect.bottom, viewportHeight) - Math.max(rect.top, 0);
        
        if (visibleWidth <= 0 || visibleHeight <= 0) {
            return false; // Not in viewport at all
        }
        
        const visibleArea = visibleWidth * visibleHeight;
        const totalArea = rect.width * rect.height;
        const visiblePercent = visibleArea / totalArea;
        
        return visiblePercent >= 0.3; // At least 30% visible
    }

    // Helper function to get correct bounding rectangle, accounting for iframes
    function getAdjustedBoundingClientRect(element, contextInfo = null) {
        const rect = element.getBoundingClientRect();
        
        // If element is in an iframe, adjust coordinates
        if (contextInfo && contextInfo.iframe) {
            const iframeRect = contextInfo.iframe.getBoundingClientRect();
            return {
                top: rect.top + iframeRect.top,
                right: rect.right + iframeRect.left,
                bottom: rect.bottom + iframeRect.top,
                left: rect.left + iframeRect.left,
                width: rect.width,
                height: rect.height
            };
        }
        
        return rect;
    }

    // Helper function to check if element is the top element at its position
    function isTopElement(element) {

        try {
            const rect = getAdjustedBoundingClientRect(element, element._contextInfo);
            const centerX = rect.left + rect.width / 2;
            const centerY = rect.top + rect.height / 2;
            
            // Check if the element is visible at its center point
            const elementsAtPoint = document.elementsFromPoint(centerX, centerY);
            
            // Nothing at this point (might be covered by an overlay)
            if (!elementsAtPoint || elementsAtPoint.length === 0) {
                return false;
            }
            
            // Handle iframe cases
            if (element._contextInfo && element._contextInfo.iframe) {
                // For elements in iframes, check if the iframe itself is the top-level element
                // then check if the element is topmost within that iframe
                const iframe = element._contextInfo.iframe;
                
                // First check if iframe is visible at the adjusted center point
                const iframeVisibleAtPoint = elementsAtPoint.includes(iframe);
                if (!iframeVisibleAtPoint) {
                    return false;
                }
                
                // Then check if element is topmost within the iframe
                try {
                    const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                    // Convert coordinates to iframe's local coordinate system
                    const iframeRect = iframe.getBoundingClientRect();
                    const localX = centerX - iframeRect.left;
                    const localY = centerY - iframeRect.top;
                    
                    const elementAtPointInIframe = iframeDoc.elementFromPoint(localX, localY);

                    if (!elementAtPointInIframe) return false;

                    return elementAtPointInIframe === element || element.contains(elementAtPointInIframe) || elementAtPointInIframe.contains(element);

                } catch (e) {
                    console.warn('Error checking element position in iframe:', e);
                    return false;
                }
            }
            
            // Handle shadow DOM cases
            if (element._contextInfo && element._contextInfo.shadowHost) {
                // For shadow DOM elements, first check if its shadow host is visible
                const shadowHost = element._contextInfo.shadowHost;
                const shadowHostVisible = elementsAtPoint.includes(shadowHost);
                
                if (!shadowHostVisible) {
                    return false;
                }
                
                // Shadow DOM elements aren't directly accessible via elementsFromPoint
                // So we're simplifying and assuming visibility based on the host visibility
                return true;
            }
            
            const elementAtPoint = document.elementFromPoint(centerX, centerY);
            
            if (!elementAtPoint) return false;
            // Check if the element at this point is our element or a descendant/ancestor of our element
            return element === elementAtPoint || 
                    element.contains(elementAtPoint) || 
                    elementAtPoint.contains(element);
            
        } catch (e) {
            console.warn('Error in isTopElement check:', e);
            return false;
        }
    }

    // Add helper function to get effective z-index
    function getEffectiveZIndex(element) {
        let current = element;
        let zIndex = 'auto';
        
        while (current && current !== document) {
            const style = window.getComputedStyle(current);
            if (style.position !== 'static' && style.zIndex !== 'auto') {
                zIndex = parseInt(style.zIndex, 10);
                break;
            }
            current = current.parentElement;
        }
        
        return zIndex === 'auto' ? 0 : zIndex;
    }

    // Function to find all interactive elements
    function findInteractiveElements() {
        console.time('findInteractiveElements');
        
        // Batch selectors for better performance
        const selectors = {
            highPriority: 'button, a[href], input:not([type="hidden"]), select, textarea, [role="button"], [role="link"], [role="checkbox"], [role="menuitem"], [role="tab"], li[role="option"], [role="switch"]',
            mediumPriority: 'details, summary, svg, path, td, [role="option"], [role="radio"], [role="switch"], [tabindex]:not([tabindex="-1"]), [aria-label], [aria-labelledby]',
            lowPriority: '[onclick], .clickable, .btn, .button, .nav-item, .menu-item'
        };
        
        // Process only elements in viewport for better performance
        const allElements = [];
        const processedElements = new Set();
        const viewportElements = [];
        
        // Function to query elements within a document or shadow root
        function queryElementsInContext(context, selector) {
            try {
                return context.querySelectorAll(selector);
            } catch (e) {
                console.warn('Error querying for elements:', e);
                return [];
            }
        }
        
        // Function to process a document or shadow root
        function processContext(context, contextInfo = { iframe: null, shadowHost: null }) {
            // Process elements in priority order
            Object.keys(selectors).forEach(priority => {
                try {
                    const elements = queryElementsInContext(context, selectors[priority]);
                    
                    for (let i = 0; i < elements.length; i++) {
                        const element = elements[i];
                        
                        // Skip already processed
                        if (processedElements.has(element)) {
                            continue;
                        }
                        
                        processedElements.add(element);
                        
                        // Add context information to the element
                        element._contextInfo = contextInfo;
                        
                        allElements.push(element);
                    }
                } catch (e) {
                    console.warn(`Error processing ${priority} elements:`, e);
                }
            });
            
            // Process shadow DOM
            const shadowHosts = queryElementsInContext(context, '*');
            for (let i = 0; i < shadowHosts.length; i++) {
                const host = shadowHosts[i];
                if (host.shadowRoot) {
                    processContext(
                        host.shadowRoot, 
                        { 
                            iframe: contextInfo.iframe, 
                            shadowHost: host 
                        }
                    );
                }
            }
        }
        
        // Process main document
        processContext(document);
        
        // Process iframes
        try {
            const iframes = document.querySelectorAll('iframe');
            for (let i = 0; i < iframes.length; i++) {
                const iframe = iframes[i];
                
                // Skip iframes from different origins
                try {
                    // This will throw if cross-origin
                    const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                    processContext(iframeDoc, { iframe: iframe, shadowHost: null });
                } catch (e) {
                    console.warn('Could not access iframe content (likely cross-origin):', e);
                }
            }
        } catch (e) {
            console.warn('Error processing iframes:', e);
        }
        
        // Process cursor:pointer elements in all contexts
        function processCursorPointerElements(context, contextInfo = { iframe: null, shadowHost: null }) {
            try {
                const allElementsInContext = queryElementsInContext(context, '*');
                
                for (let i = 0; i < allElementsInContext.length; i++) {
                    const element = allElementsInContext[i];
                    
                    // Skip already processed
                    if (processedElements.has(element)) {
                        continue;
                    }
                    
                    // Quick check before expensive operations
                    const rect = getAdjustedBoundingClientRect(element, contextInfo);
                    if (!isInViewport(rect)) {
                        continue;
                    }
                    
                    // Check style
                    if (isTopElement(element) && window.getComputedStyle(element).cursor === 'pointer') {
                        // Add context information to the element
                        element._contextInfo = contextInfo;
                        
                        processedElements.add(element);
                        allElements.push(element);
                        
                        viewportElements.push({
                            element: element,
                            rect: rect,
                            weight: 1,
                            zIndex: getEffectiveZIndex(element)
                        });
                    }
                    
                    // Process shadow DOM of this element
                    if (element.shadowRoot) {
                        processCursorPointerElements(
                            element.shadowRoot,
                            {
                                iframe: contextInfo.iframe,
                                shadowHost: element
                            }
                        );
                    }
                }
            } catch (e) {
                console.warn('Error processing cursor:pointer elements:', e);
            }
        }
        
        // Process cursor:pointer elements in the main document
        processCursorPointerElements(document);
        
        // Process cursor:pointer elements in iframes
        try {
            const iframes = document.querySelectorAll('iframe');
            for (let i = 0; i < iframes.length; i++) {
                const iframe = iframes[i];
                try {
                    const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                    processCursorPointerElements(iframeDoc, { iframe: iframe, shadowHost: null });
                } catch (e) {
                    // Already logged in previous iframe processing
                }
            }
        } catch (e) {
            // Already logged in previous iframe processing
        }
        
        // Filter for visible elements
        for (let i = 0; i < allElements.length; i++) {
            const element = allElements[i];
            
            // Skip detailed processing if not in viewport
            const rect = getAdjustedBoundingClientRect(element, element._contextInfo);
            if (!isInViewport(rect)) {
                continue;
            }
            
            // Skip disabled elements
            if (element.hasAttribute('disabled') || 
                element.getAttribute('aria-disabled') === 'true') {
                continue;
            }

            // Add check for too-large elements
            if (isElementTooBig(rect)) {
                continue; // Skip elements that cover more than 50% of viewport
            }
            
            // Check if the element is the top element at its position
            if (!isTopElement(element)) {
                continue;
            }
            
            // Calculate element weight
            let weight = elementWeights[element.tagName.toLowerCase()] || 1;
            
            // Boost weight for elements with specific attributes
            if (element.getAttribute('role') === 'button') weight = Math.max(weight, 8);
            if (element.hasAttribute('onclick')) weight = Math.max(weight, 7);
            if (element.hasAttribute('href')) weight = Math.max(weight, 8);
            if (window.getComputedStyle(element).cursor === 'pointer') weight = Math.max(weight, 4);
            
            // Add to viewport elements
            viewportElements.push({
                element: element,
                rect: rect,
                weight: weight,
                zIndex: getEffectiveZIndex(element)
            });

            // Add this to the code that processes each element
            element.setAttribute('data-element-index', i);

            // Add a unique identifier attribute to the element
            const uniqueId = generateUniqueId();
            element.setAttribute('data-browser-agent-id', uniqueId);
        }
        
        console.timeEnd('findInteractiveElements');
        console.log(`Found ${viewportElements.length} interactive elements in viewport (out of ${allElements.length} total)`);
        return viewportElements;
    }

    // Calculate Intersection over Union (IoU) between two rectangles
    function calculateIoU(rect1, rect2) {
        // Calculate area of each rectangle
        const area1 = (rect1.right - rect1.left) * (rect1.bottom - rect1.top);
        const area2 = (rect2.right - rect2.left) * (rect2.bottom - rect2.top);
        
        // Calculate intersection
        const intersectLeft = Math.max(rect1.left, rect2.left);
        const intersectTop = Math.max(rect1.top, rect2.top);
        const intersectRight = Math.min(rect1.right, rect2.right);
        const intersectBottom = Math.min(rect1.bottom, rect2.bottom);
        
        // Check if intersection exists
        if (intersectRight < intersectLeft || intersectBottom < intersectTop) {
            return 0; // No intersection
        }
        
        // Calculate area of intersection
        const intersectionArea = (intersectRight - intersectLeft) * (intersectBottom - intersectTop);
        
        // Calculate union area
        const unionArea = area1 + area2 - intersectionArea;
        
        // Calculate IoU
        return intersectionArea / unionArea;
    }

    // Check if rect1 is fully contained within rect2
    function isFullyContained(rect1, rect2) {
        return rect1.left >= rect2.left && 
               rect1.right <= rect2.right &&
               rect1.top >= rect2.top &&
               rect1.bottom <= rect2.bottom;
    }

    // Filter overlapping elements using weight and IoU
    function filterOverlappingElements(elements) {
        console.time('filterOverlappingElements');
        
        // Sort by area (descending - larger first), then by weight (descending) for same area
        elements.sort((a, b) => {
            // Calculate areas
            const areaA = a.rect.width * a.rect.height;
            const areaB = b.rect.width * b.rect.height;
            
            // Sort by area first (larger area first)
            if (areaB !== areaA) {
                return areaB - areaA; // Larger area first
            }
            
            // For same area, sort by weight (higher weight first)
            return b.weight - a.weight;
        });
        
        const filteredElements = [];
        const iouThreshold = 0.7; // Threshold for considering elements as overlapping
        
        // Add elements one by one, checking against already added elements
        for (let i = 0; i < elements.length; i++) {
            const current = elements[i];
            let shouldAdd = true;
            
            // For each element already in our filtered list
            for (let j = 0; j < filteredElements.length; j++) {
                const existing = filteredElements[j];
                
                // Convert DOMRect to plain object for IoU calculation
                const currentRect = {
                    left: current.rect.left,
                    top: current.rect.top,
                    right: current.rect.right,
                    bottom: current.rect.bottom
                };
                
                const existingRect = {
                    left: existing.rect.left,
                    top: existing.rect.top,
                    right: existing.rect.right,
                    bottom: existing.rect.bottom
                };
                
                // Check for high overlap
                const iou = calculateIoU(currentRect, existingRect);
                if (iou > iouThreshold) {
                    shouldAdd = false;
                    break;
                }
                
                // Check if current element is fully contained within an existing element with higher weight
                if (existing.weight >= current.weight && 
                    isFullyContained(currentRect, existingRect) && 
                    existing.zIndex === current.zIndex) {
                    shouldAdd = false;
                    break;
                }
            }
            
            if (shouldAdd) {
                filteredElements.push(current);
            }
        }
        
        console.timeEnd('filterOverlappingElements');
        return filteredElements;
    }

    // Main function to get interactive elements with coordinates
    function getInteractiveElementsData() {
        // Find all potential interactive elements
        const potentialElements = findInteractiveElements();
        
        // Filter out overlapping elements
        const filteredElements = filterOverlappingElements(potentialElements);
        console.log(`Filtered to ${filteredElements.length} non-overlapping elements`);
        
        // Sort elements by position (top-to-bottom, left-to-right)
        const sortedElements = sortElementsByPosition(filteredElements);
        
        // Prepare result with viewport metadata
        const result = {
            viewport: {
                width: window.innerWidth,
                height: window.innerHeight,
                scrollX: Math.round(window.scrollX),
                scrollY: Math.round(window.scrollY),
                devicePixelRatio: window.devicePixelRatio || 1,
                scrollDistanceAboveViewport: Math.round(window.scrollY),
                scrollDistanceBelowViewport: Math.round(document.documentElement.scrollHeight - window.scrollY - window.innerHeight)
            },
            elements: []
        };
        
        // Process each interactive element (now sorted by position)
        sortedElements.forEach((item, index) => {
            const element = item.element;
            const rect = item.rect;
            
            // Ensure each element has a index_id
            let browserId = element.getAttribute('data-browser-agent-id');

            if (!browserId) {
                const uniqueId = generateUniqueId();
                element.setAttribute('data-browser-agent-id', uniqueId);
                browserId = uniqueId;
            }
            
            // Get element text (direct or from children)
            let text = element.innerText || '';
            if (!text) {
                const textNodes = Array.from(element.childNodes)
                    .filter(node => node.nodeType === Node.TEXT_NODE)
                    .map(node => node.textContent.trim())
                    .filter(content => content.length > 0);
                text = textNodes.join(' ');
            }
            
            // Extract important attributes
            const attributes = {};
            ['id', 'class', 'href', 'type', 'name', 'value', 'placeholder', 'aria-label', 'title', 'role'].forEach(attr => {
                if (element.hasAttribute(attr)) {
                    attributes[attr] = element.getAttribute(attr);
                }
            });
            
            // Determine input type and element role more clearly
            let elementType = element.tagName.toLowerCase();
            let inputType = null;

            // Handle input elements specifically
            if (elementType === 'input' && element.hasAttribute('type')) {
                inputType = element.getAttribute('type').toLowerCase();
            }
            
            // scaledRect is for coordinates scaled to 1024 width
            const scaleFactor = 1024 / window.innerWidth
            const scaledRect = {
                left: Math.round(rect.left * scaleFactor),
                top: Math.round(rect.top * scaleFactor),
                right: Math.round(rect.right * scaleFactor),
                bottom: Math.round(rect.bottom * scaleFactor),
                width: Math.round(rect.width * scaleFactor),
                height: Math.round(rect.height * scaleFactor),
            }
            
            // Create element data object
            const elementData = {
                tagName: elementType,
                text: text.trim(),
                attributes,
                index,
                weight: item.weight,
                browserAgentId: browserId,  // Use the guaranteed ID
                inputType: inputType,  // Add specific input type
                viewport: {
                    x: Math.round(rect.left),
                    y: Math.round(rect.top),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height)
                },
                page: {
                    x: Math.round(rect.left + window.scrollX),
                    y: Math.round(rect.top + window.scrollY),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height)
                },
                center: {
                    x: Math.round(rect.left + rect.width/2),
                    y: Math.round(rect.top + rect.height/2)
                },
                rect: scaledRect,
                zIndex: item.zIndex
            };
            
            // Add context information for iframe or shadow DOM if applicable
            if (element._contextInfo) {
                elementData.context = {};
                
                // Add iframe information if element is within an iframe
                if (element._contextInfo.iframe) {
                    const iframeRect = element._contextInfo.iframe.getBoundingClientRect();
                    elementData.context.iframe = {
                        id: element._contextInfo.iframe.id || null,
                        name: element._contextInfo.iframe.name || null,
                        src: element._contextInfo.iframe.src || null,
                        rect: {
                            x: Math.round(iframeRect.left),
                            y: Math.round(iframeRect.top),
                            width: Math.round(iframeRect.width),
                            height: Math.round(iframeRect.height)
                        }
                    };
                }
                
                // Add shadow DOM information if element is within a shadow DOM
                if (element._contextInfo.shadowHost) {
                    const shadowHost = element._contextInfo.shadowHost;
                    const shadowHostRect = shadowHost.getBoundingClientRect();
                    elementData.context.shadowDOM = {
                        hostTagName: shadowHost.tagName.toLowerCase(),
                        hostId: shadowHost.id || null,
                        hostRect: {
                            x: Math.round(shadowHostRect.left),
                            y: Math.round(shadowHostRect.top),
                            width: Math.round(shadowHostRect.width),
                            height: Math.round(shadowHostRect.height)
                        }
                    };
                }
            }
            
            result.elements.push(elementData);
            
        });
        
        return result;
    }

    // Add new function to sort elements by position
    function sortElementsByPosition(elements) {
        // Define what "same row" means (elements within this Y-distance are considered in the same row)
        const ROW_THRESHOLD = 20; // pixels
        
        // First, group elements into rows based on their Y position
        const rows = [];
        let currentRow = [];
        
        // Copy elements to avoid modifying the original array
        const sortedByY = [...elements].sort((a, b) => {
            return a.rect.top - b.rect.top;
        });
        
        // Group into rows
        sortedByY.forEach(element => {
            if (currentRow.length === 0) {
                // Start a new row
                currentRow.push(element);
            } else {
                // Check if this element is in the same row as the previous ones
                const lastElement = currentRow[currentRow.length - 1];
                if (Math.abs(element.rect.top - lastElement.rect.top) <= ROW_THRESHOLD) {
                    // Same row
                    currentRow.push(element);
                } else {
                    // New row
                    rows.push([...currentRow]);
                    currentRow = [element];
                }
            }
        });
        
        // Add the last row if not empty
        if (currentRow.length > 0) {
            rows.push(currentRow);
        }
        
        // Sort each row by X position (left to right)
        rows.forEach(row => {
            row.sort((a, b) => a.rect.left - b.rect.left);
        });
        
        // Flatten the rows back into a single array
        return rows.flat();
    }

    // Execute and measure performance
    console.time('getInteractiveElements');
    const result = getInteractiveElementsData();
    console.timeEnd('getInteractiveElements');
    console.timeEnd('totalExecutionTime');

    return result;
};   