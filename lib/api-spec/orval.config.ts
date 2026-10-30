import { defineConfig, InputTransformerFn, type ZodOptions } from "orval";
import path from "path";

const root = path.resolve(__dirname, "..", "..");
const apiClientReactSrc = path.resolve(root, "lib", "api-client-react", "src");
const apiZodSrc = path.resolve(root, "lib", "api-zod", "src");

// Our exports make assumptions about the title of the API being "Api" (i.e. generated output is `api.ts`).
const titleTransformer: InputTransformerFn = (config) => {
  config.info ??= {};
  config.info.title = "Api";

  return config;
};

// Orval8.30 drops strictness for zero-property objects. Its supported `never`
// value schema emits an empty JSON record: accepts {} and rejects JSON-valued keys.
// Orval emits optional never; non-JSON undefined-valued own keys are outside wire scope.
// This is Zod-only input lowering; published OpenAPI remains additionalProperties:false.
const levelUpZodTransformer: InputTransformerFn = (config) => {
  const transformed = titleTransformer(config);
  const empty = transformed.components?.schemas?.BarbarianLevel2Choices;
  if (!empty || "$ref" in empty || empty.additionalProperties !== false
      || Object.keys(empty.properties ?? {}).length !== 0) {
    throw new Error("Expected strict empty BarbarianLevel2Choices component");
  }
  empty.additionalProperties = { type: "never" } as never;
  return transformed;
};

// Orval 8.30 normalizes omitted operation-level coerce entries to false.
// Share the inherited values explicitly when adding only request strictness;
// the Zod version remains output-level because operation version is unsupported.
const sharedZodCoerce: ZodOptions["coerce"] = {
  query: ['boolean', 'number', 'string'],
  param: ['boolean', 'number', 'string'],
  body: ['bigint', 'date'],
  response: ['bigint', 'date'],
};

export default defineConfig({
  "api-client-react": {
    input: {
      target: "./openapi.yaml",
      override: {
        transformer: titleTransformer,
      },
    },
    output: {
      workspace: apiClientReactSrc,
      target: "generated",
      client: "react-query",
      mode: "split",
      baseUrl: "/api",
      clean: true,
      prettier: true,
      override: {
        fetch: {
          includeHttpResponseReturnType: false,
        },
        mutator: {
          path: path.resolve(apiClientReactSrc, "custom-fetch.ts"),
          name: "customFetch",
        },
      },
    },
  },
  zod: {
    input: {
      target: "./openapi.yaml",
      override: {
        transformer: levelUpZodTransformer,
      },
    },
    output: {
      workspace: apiZodSrc,
      client: "zod",
      target: "generated",
      schemas: { path: "generated/types", type: "typescript" },
      mode: "split",
      clean: true,
      prettier: true,
      override: {
        operations: {
          playGameTurn: { zod: { coerce: sharedZodCoerce, strict: { body: true } } },
          playLegacyTurn: { zod: { coerce: sharedZodCoerce, strict: { body: true } } },
          createCampaign: { zod: { strict: { body: true } } },
          createLegacyCampaign: { zod: { strict: { body: true } } },
          // Empty noncaster choices must not swallow invalid objects in the union.
          applyGameSessionLevelUp: { zod: {
            strict: { body: true },
          } },
        },
        zod: {
          // Orval resolves `auto` from lib/api-spec/package.json, which has no
          // zod dependency, so orval >= 8.23 falls back to Zod 4 syntax while
          // the catalog installs zod 3. Pin to match the catalog.
          version: 3,
          coerce: sharedZodCoerce,
        },
        useDates: true,
        useBigInt: true,
      },
    },
  },
});
