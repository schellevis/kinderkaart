/**
 * URL safety helpers.
 */

/**
 * Returns the URL string only if it uses the http: or https: protocol.
 * Returns null for javascript:, data:, relative URLs, or unparseable strings.
 */
export function safeHttpUrl(value: string): string | null {
  try {
    const u = new URL(value);
    return u.protocol === "http:" || u.protocol === "https:" ? u.toString() : null;
  } catch {
    return null;
  }
}
