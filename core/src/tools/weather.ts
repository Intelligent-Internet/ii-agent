import { z } from 'zod';

export const WeatherToolSchema = z.object({
  location: z.string().describe("The city and state, e.g. San Francisco, CA"),
  unit: z.enum(["celsius", "fahrenheit"]).optional().describe("The unit of temperature, either 'celsius' or 'fahrenheit'"),
});

export const weatherToolDefinition = {
  name: "get_current_weather",
  description: "Get the current weather in a given location",
  schema: WeatherToolSchema, // We will use zod-to-json-schema to convert this at runtime if needed, or manual definition
};
