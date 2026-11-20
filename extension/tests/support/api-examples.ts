import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";

/**
 * The server's examples of every request the clipper makes and the reply it
 * gets (`server/tests/api_examples/`, plan 012 M4). The server's tests replay
 * each one against its views; the extension's read the same files, so the two
 * sides cannot disagree about a message's shape without a test failing.
 */
export const API_EXAMPLES = resolve(
  import.meta.dirname,
  "../../../server/tests/api_examples",
);

export interface ApiExample {
  readonly description: string;
  readonly request: {
    readonly method: string;
    readonly path: string;
    readonly headers: Readonly<Record<string, string>>;
    readonly body?: unknown;
  };
  readonly response: {
    readonly status: number;
    readonly headers?: Readonly<Record<string, string>>;
    readonly body: unknown;
  };
}

export function apiExample(name: string): ApiExample {
  return JSON.parse(
    readFileSync(resolve(API_EXAMPLES, name), "utf8"),
  ) as ApiExample;
}

export function apiExampleNames(): string[] {
  return readdirSync(API_EXAMPLES)
    .filter((name) => name.endsWith(".json"))
    .sort();
}
