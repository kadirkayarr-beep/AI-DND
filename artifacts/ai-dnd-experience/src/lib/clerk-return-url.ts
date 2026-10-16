export function clerkReturnUrl(baseUrl: string, pageUrl: string): string {
  if (!baseUrl.startsWith("/")) {
    throw new Error("Clerk return base must be root-relative.");
  }
  const normalized = baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`;
  const url = new URL(normalized, pageUrl);
  url.search = "";
  url.hash = "";
  if (url.pathname !== normalized) {
    throw new Error("Clerk return URL must contain the app root once.");
  }
  return url.href;
}
