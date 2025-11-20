import { getQuickJS, QuickJSContext, QuickJSWASMModule } from 'quickjs-emscripten';
import { z } from 'zod';

export const codeExecutorToolDefinition = {
  name: 'code_interpreter',
  description: 'Execute JavaScript code in a secure sandbox. Use this to perform calculations, data manipulation, or logic that is difficult to do with a pure LLM.',
  schema: z.object({
    code: z.string().describe('The JavaScript code to execute. The last expression will be returned. Use console.log for intermediate output.'),
  }),
};

let quickJS: QuickJSWASMModule | undefined;

async function getQuickJSInstance() {
  if (!quickJS) {
    quickJS = await getQuickJS();
  }
  return quickJS;
}

export async function executeCode(input: { code: string }) {
  const QuickJS = await getQuickJSInstance();
  const vm = QuickJS.newContext();

  const logs: string[] = [];
  const logHandle = vm.newFunction('log', (...args) => {
    const nativeArgs = args.map(arg => vm.dump(arg));
    logs.push(nativeArgs.map(arg =>
      typeof arg === 'object' ? JSON.stringify(arg) : String(arg)
    ).join(' '));
  });

  const consoleHandle = vm.newObject();
  vm.setProp(consoleHandle, 'log', logHandle);
  vm.setProp(vm.global, 'console', consoleHandle);

  consoleHandle.dispose();
  logHandle.dispose();

  try {
    const result = vm.evalCode(input.code);

    if (result.error) {
      const error = vm.dump(result.error);
      result.error.dispose();

      // If error is an object (like Error instance), quickjs dump might just return {} or [object Object] if not handled carefully.
      // But usually it dumps JSON structure.
      // Let's try to extract message if it's an Error object.
      let errorMessage = String(error);
      if (typeof error === 'object' && error !== null) {
          if ('message' in error) {
              errorMessage = (error as any).message;
          } else if ('name' in error && 'message' in error) {
             errorMessage = `${(error as any).name}: ${(error as any).message}`;
          } else {
             errorMessage = JSON.stringify(error);
          }
      }

      return {
          error: errorMessage,
          logs
      };
    }

    const value = vm.dump(result.value);
    result.value.dispose();

    return {
        result: value,
        logs
    };
  } catch (err) {
      return {
          error: String(err),
          logs
      }
  } finally {
    vm.dispose();
  }
}
