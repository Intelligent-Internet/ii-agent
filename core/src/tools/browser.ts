import { chromium, Browser, Page } from 'playwright';
import { z } from 'zod';

export const browserToolDefinitions = [
    {
        name: 'browser_open',
        description: 'Open a website and extract its content as Markdown. Use this to read documentation, news, or any web page.',
        schema: z.object({
            url: z.string().url().describe('The URL to visit.'),
        })
    },
];

let browser: Browser | null = null;

async function getBrowser() {
    if (!browser) {
        browser = await chromium.launch({
            headless: true,
        });
    }
    return browser;
}

export async function browserOpen(input: { url: string }) {
    const b = await getBrowser();
    const context = await b.newContext({
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    });
    const page = await context.newPage();

    try {
        await page.goto(input.url, { waitUntil: 'domcontentloaded', timeout: 30000 });

        // Use evaluate with a simple function to avoid transpilation issues with 'tsx' or closures
        const content = await page.evaluate(() => {
            // Remove scripts and styles
            const elements = document.querySelectorAll('script, style, nav, footer, iframe, noscript');
            for (const el of elements) {
                el.remove();
            }
            return document.body.innerText;
        });

        const title = await page.title();

        return {
            title,
            content: content.replace(/\s+/g, ' ').trim(),
            url: page.url()
        };

    } catch (error) {
        return {
            error: `Failed to load ${input.url}: ${String(error)}`
        };
    } finally {
        await context.close();
    }
}

export const browserHandlers = {
    'browser_open': browserOpen
};
