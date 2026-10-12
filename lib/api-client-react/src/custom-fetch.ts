export type CustomFetchOptions = RequestInit & {
  responseType?: "json" | "text" | "blob" | "auto";
};

export type ErrorType<T = unknown> = ApiError<T>;

export type BodyType<T> = T;

export type AuthTokenGetter = () => Promise<string | null> | string | null;

const NO_BODY_STATUS = new Set([204, 205, 304]);
const DEFAULT_JSON_ACCEPT = "application/json, application/problem+json";

// ---------------------------------------------------------------------------
// Module-level configuration
// ---------------------------------------------------------------------------

let _baseUrl: string | null = null;
let _authTokenGetter: AuthTokenGetter | null = null;

/**
 * Set a base URL that is prepended to every relative request URL
 * (i.e. paths that start with `/`).
 *
 * Useful for Expo bundles that need to call a remote API server.
 * Pass `null` to clear the base URL.
 */
export function setBaseUrl(url: string | null): void {
  _baseUrl = url ? url.replace(/\/+$/, "") : null;
}

/**
 * Register a getter that supplies a fresh bearer token for protected
 * same-origin AI-DND API calls. The getter is invoked per request.
 * Returned values are not stored. Pass `null` to clear the getter.
 */
export function setAuthTokenGetter(getter: AuthTokenGetter | null): void {
  _authTokenGetter = getter;
}

const PUBLIC_API_PATHS = new Set([
  "/api/health",
  "/api/game/health",
  "/api/character-options",
  "/api/game/character-options",
  "/api/character-creation-catalog",
  "/api/game/character-creation-catalog",
  "/api/campaign-start-options",
  "/api/game/campaign-start-options",
  "/api/logout",
  "/api/game/logout",
]);

const CREDENTIAL_QUERY_KEYS = ["access_token", "token", "jwt", "id_token"];
const RELATIVE_DESTINATION_BASE = "http://ai-dnd.local";
const AUTHENTICATION_MESSAGE = "Oturum doğrulanmadan maceralar açılmaz.";
const MAX_BEARER_TOKEN_LENGTH = 8192;

export type ApiDestination = "public" | "protected" | "external" | "foreign-api";

export class ApiRequestError extends Error {
  readonly name = "ApiRequestError";
  readonly status = 401;
  readonly code: "authentication_required" | "authentication_changed" | "unapproved_destination";

  constructor(code: ApiRequestError["code"]) {
    super(code === "unapproved_destination" ? "Bu istek gönderilmedi." : AUTHENTICATION_MESSAGE);
    this.code = code;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

let authEpoch = 0;
let authAbort = new AbortController();

export function currentAuthEpoch(): number {
  return authEpoch;
}

export function rotateAuthEpoch(): number {
  authEpoch += 1;
  authAbort.abort();
  authAbort = new AbortController();
  return authEpoch;
}

function pageOrigin(): string | null {
  const origin = globalThis.window?.location?.origin;
  return typeof origin === "string" && origin.length > 0 ? origin : null;
}

export function classifyApiDestination(url: string): ApiDestination {
  let parsed: URL;
  let relative = false;
  try {
    if (url.startsWith("/") && !url.startsWith("//")) {
      parsed = new URL(url, RELATIVE_DESTINATION_BASE);
      relative = true;
    } else {
      parsed = new URL(url);
    }
  } catch {
    return "external";
  }
  const path = parsed.pathname.replace(/\/+$/, "") || "/";
  const isApi = path === "/api" || path.startsWith("/api/");
  if (!isApi) return "external";
  if (!relative) {
    const origin = pageOrigin();
    if (!origin || parsed.origin !== origin) return "foreign-api";
  }
  return PUBLIC_API_PATHS.has(path) ? "public" : "protected";
}

function stripCredentialQuery(url: string): string {
  let parsed: URL;
  let relative = false;
  try {
    if (url.startsWith("/") && !url.startsWith("//")) {
      parsed = new URL(url, RELATIVE_DESTINATION_BASE);
      relative = true;
    } else {
      parsed = new URL(url);
    }
  } catch {
    return url;
  }
  for (const key of CREDENTIAL_QUERY_KEYS) parsed.searchParams.delete(key);
  parsed.hash = "";
  if (relative) return `${parsed.pathname}${parsed.search}`;
  return parsed.toString();
}

function usableBearerToken(token: string | null): token is string {
  return typeof token === "string"
    && token.length > 0
    && token.length <= MAX_BEARER_TOKEN_LENGTH
    && !/\s/.test(token);
}

async function readBearerToken(): Promise<string | null> {
  if (!_authTokenGetter) return null;
  try {
    const token = await _authTokenGetter();
    return usableBearerToken(token) ? token : null;
  } catch {
    return null;
  }
}

function combineSignals(authSignal: AbortSignal, callerSignal: AbortSignal | null | undefined): AbortSignal {
  if (!callerSignal) return authSignal;
  if (typeof AbortSignal.any === "function") return AbortSignal.any([authSignal, callerSignal]);
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (authSignal.aborted || callerSignal.aborted) controller.abort();
  else {
    authSignal.addEventListener("abort", abort, { once: true });
    callerSignal.addEventListener("abort", abort, { once: true });
  }
  return controller.signal;
}

function isRequest(input: RequestInfo | URL): input is Request {
  return typeof Request !== "undefined" && input instanceof Request;
}

function resolveMethod(input: RequestInfo | URL, explicitMethod?: string): string {
  if (explicitMethod) return explicitMethod.toUpperCase();
  if (isRequest(input)) return input.method.toUpperCase();
  return "GET";
}

// Use loose check for URL — some runtimes (e.g. React Native) polyfill URL
// differently, so `instanceof URL` can fail.
function isUrl(input: RequestInfo | URL): input is URL {
  return typeof URL !== "undefined" && input instanceof URL;
}

function applyBaseUrl(input: RequestInfo | URL): RequestInfo | URL {
  if (!_baseUrl) return input;
  const url = resolveUrl(input);
  // Only prepend to relative paths (starting with /)
  if (!url.startsWith("/")) return input;

  const absolute = `${_baseUrl}${url}`;
  if (typeof input === "string") return absolute;
  if (isUrl(input)) return new URL(absolute);
  return new Request(absolute, input as Request);
}

function resolveUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (isUrl(input)) return input.toString();
  return input.url;
}

function mergeHeaders(...sources: Array<HeadersInit | undefined>): Headers {
  const headers = new Headers();

  for (const source of sources) {
    if (!source) continue;
    new Headers(source).forEach((value, key) => {
      headers.set(key, value);
    });
  }

  return headers;
}

function getMediaType(headers: Headers): string | null {
  const value = headers.get("content-type");
  return value ? value.split(";", 1)[0].trim().toLowerCase() : null;
}

function isJsonMediaType(mediaType: string | null): boolean {
  return mediaType === "application/json" || Boolean(mediaType?.endsWith("+json"));
}

function isTextMediaType(mediaType: string | null): boolean {
  return Boolean(
    mediaType &&
      (mediaType.startsWith("text/") ||
        mediaType === "application/xml" ||
        mediaType === "text/xml" ||
        mediaType.endsWith("+xml") ||
        mediaType === "application/x-www-form-urlencoded"),
  );
}

// Use strict equality: in browsers, `response.body` is `null` when the
// response genuinely has no content.  In React Native, `response.body` is
// always `undefined` because the ReadableStream API is not implemented —
// even when the response carries a full payload readable via `.text()` or
// `.json()`.  Loose equality (`== null`) matches both `null` and `undefined`,
// which causes every React Native response to be treated as empty.
function hasNoBody(response: Response, method: string): boolean {
  if (method === "HEAD") return true;
  if (NO_BODY_STATUS.has(response.status)) return true;
  if (response.headers.get("content-length") === "0") return true;
  if (response.body === null) return true;
  return false;
}

function stripBom(text: string): string {
  return text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
}

function looksLikeJson(text: string): boolean {
  const trimmed = text.trimStart();
  return trimmed.startsWith("{") || trimmed.startsWith("[");
}

function getStringField(value: unknown, key: string): string | undefined {
  if (!value || typeof value !== "object") return undefined;

  const candidate = (value as Record<string, unknown>)[key];
  if (typeof candidate !== "string") return undefined;

  const trimmed = candidate.trim();
  return trimmed === "" ? undefined : trimmed;
}

function truncate(text: string, maxLength = 300): string {
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
}

function buildErrorMessage(response: Response, data: unknown): string {
  const prefix = `HTTP ${response.status} ${response.statusText}`;

  if (typeof data === "string") {
    const text = data.trim();
    return text ? `${prefix}: ${truncate(text)}` : prefix;
  }

  const title = getStringField(data, "title");
  const detail = getStringField(data, "detail");
  const message =
    getStringField(data, "message") ??
    getStringField(data, "error_description") ??
    getStringField(data, "error");

  if (title && detail) return `${prefix}: ${title} — ${detail}`;
  if (detail) return `${prefix}: ${detail}`;
  if (message) return `${prefix}: ${message}`;
  if (title) return `${prefix}: ${title}`;

  return prefix;
}

export class ApiError<T = unknown> extends Error {
  readonly name = "ApiError";
  readonly status: number;
  readonly statusText: string;
  readonly data: T | null;
  readonly headers: Headers;
  readonly response: Response;
  readonly method: string;
  readonly url: string;

  constructor(
    response: Response,
    data: T | null,
    requestInfo: { method: string; url: string },
  ) {
    super(buildErrorMessage(response, data));
    Object.setPrototypeOf(this, new.target.prototype);

    this.status = response.status;
    this.statusText = response.statusText;
    this.data = data;
    this.headers = response.headers;
    this.response = response;
    this.method = requestInfo.method;
    this.url = response.url || requestInfo.url;
  }
}

export class ResponseParseError extends Error {
  readonly name = "ResponseParseError";
  readonly status: number;
  readonly statusText: string;
  readonly headers: Headers;
  readonly response: Response;
  readonly method: string;
  readonly url: string;
  readonly rawBody: string;
  readonly cause: unknown;

  constructor(
    response: Response,
    rawBody: string,
    cause: unknown,
    requestInfo: { method: string; url: string },
  ) {
    super(
      `Failed to parse response from ${requestInfo.method} ${response.url || requestInfo.url} ` +
        `(${response.status} ${response.statusText}) as JSON`,
    );
    Object.setPrototypeOf(this, new.target.prototype);

    this.status = response.status;
    this.statusText = response.statusText;
    this.headers = response.headers;
    this.response = response;
    this.method = requestInfo.method;
    this.url = response.url || requestInfo.url;
    this.rawBody = rawBody;
    this.cause = cause;
  }
}

async function parseJsonBody(
  response: Response,
  requestInfo: { method: string; url: string },
): Promise<unknown> {
  const raw = await response.text();
  const normalized = stripBom(raw);

  if (normalized.trim() === "") {
    return null;
  }

  try {
    return JSON.parse(normalized);
  } catch (cause) {
    throw new ResponseParseError(response, raw, cause, requestInfo);
  }
}

async function parseErrorBody(response: Response, method: string): Promise<unknown> {
  if (hasNoBody(response, method)) {
    return null;
  }

  const mediaType = getMediaType(response.headers);

  // Fall back to text when blob() is unavailable (e.g. some React Native builds).
  if (mediaType && !isJsonMediaType(mediaType) && !isTextMediaType(mediaType)) {
    return typeof response.blob === "function" ? response.blob() : response.text();
  }

  const raw = await response.text();
  const normalized = stripBom(raw);
  const trimmed = normalized.trim();

  if (trimmed === "") {
    return null;
  }

  if (isJsonMediaType(mediaType) || looksLikeJson(normalized)) {
    try {
      return JSON.parse(normalized);
    } catch {
      return raw;
    }
  }

  return raw;
}

function inferResponseType(response: Response): "json" | "text" | "blob" {
  const mediaType = getMediaType(response.headers);

  if (isJsonMediaType(mediaType)) return "json";
  if (isTextMediaType(mediaType) || mediaType == null) return "text";
  return "blob";
}

async function parseSuccessBody(
  response: Response,
  responseType: "json" | "text" | "blob" | "auto",
  requestInfo: { method: string; url: string },
): Promise<unknown> {
  if (hasNoBody(response, requestInfo.method)) {
    return null;
  }

  const effectiveType =
    responseType === "auto" ? inferResponseType(response) : responseType;

  switch (effectiveType) {
    case "json":
      return parseJsonBody(response, requestInfo);

    case "text": {
      const text = await response.text();
      return text === "" ? null : text;
    }

    case "blob":
      if (typeof response.blob !== "function") {
        throw new TypeError(
          "Blob responses are not supported in this runtime. " +
            "Use responseType \"json\" or \"text\" instead.",
        );
      }
      return response.blob();
  }
}

export async function customFetch<T = unknown>(
  input: RequestInfo | URL,
  options: CustomFetchOptions = {},
): Promise<T> {
  input = applyBaseUrl(input);
  const { responseType = "auto", headers: headersInit, ...init } = options;

  const method = resolveMethod(input, init.method);

  if (init.body != null && (method === "GET" || method === "HEAD")) {
    throw new TypeError(`customFetch: ${method} requests cannot have a body.`);
  }

  const headers = mergeHeaders(isRequest(input) ? input.headers : undefined, headersInit);

  if (
    typeof init.body === "string" &&
    !headers.has("content-type") &&
    looksLikeJson(init.body)
  ) {
    headers.set("content-type", "application/json");
  }

  if (responseType === "json" && !headers.has("accept")) {
    headers.set("accept", DEFAULT_JSON_ACCEPT);
  }

  const destinationUrl = stripCredentialQuery(resolveUrl(input));
  const destination = classifyApiDestination(destinationUrl);
  headers.delete("authorization");

  let credentials: RequestCredentials = init.credentials ?? "include";
  let redirectMode: RequestRedirect | undefined = init.redirect;
  let signal: AbortSignal | null | undefined = init.signal;
  const epoch = authEpoch;
  const epochSignal = authAbort.signal;

  if (destination === "foreign-api") {
    throw new ApiRequestError("unapproved_destination");
  }

  if (destination === "external") {
    headers.delete("cookie");
    credentials = "omit";
    redirectMode = "error";
  }

  if (destination === "protected") {
    if (epoch !== authEpoch || epochSignal.aborted) {
      throw new ApiRequestError("authentication_changed");
    }
    const token = await readBearerToken();
    if (epoch !== authEpoch || epochSignal.aborted) {
      throw new ApiRequestError("authentication_changed");
    }
    if (!token) throw new ApiRequestError("authentication_required");
    headers.delete("cookie");
    headers.set("Authorization", `Bearer ${token}`);
    credentials = "omit";
    redirectMode = "error";
    signal = combineSignals(epochSignal, init.signal);
  }

  if (
    (destination === "public" || destination === "protected")
    && ["POST", "PUT", "PATCH", "DELETE"].includes(method)
    && !headers.has("x-ai-dnd-request")
  ) {
    headers.set("X-AI-DND-Request", "1");
  }

  const requestInfo = { method, url: destinationUrl };
  const fetchInput: RequestInfo | URL = typeof input === "string" || isUrl(input)
    ? destinationUrl
    : new Request(destinationUrl, input);

  let response: Response;
  try {
    response = await fetch(fetchInput, {
      ...init,
      method,
      headers,
      credentials,
      redirect: redirectMode,
      signal,
    });
  } catch (error) {
    if (destination === "protected" && (epoch !== authEpoch || epochSignal.aborted)) {
      throw new ApiRequestError("authentication_changed");
    }
    throw error;
  }

  if (destination === "protected" && epoch !== authEpoch) {
    throw new ApiRequestError("authentication_changed");
  }

  if (!response.ok) {
    const errorData = await parseErrorBody(response, method);
    throw new ApiError(response, errorData, requestInfo);
  }

  const body = (await parseSuccessBody(response, responseType, requestInfo)) as T;
  if (destination === "protected" && epoch !== authEpoch) {
    throw new ApiRequestError("authentication_changed");
  }
  return body;
}
