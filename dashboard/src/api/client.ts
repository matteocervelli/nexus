import { ApiError } from "./errors";

const BASE_URL: string =
  (import.meta.env["VITE_API_URL"] as string | undefined) ?? "";

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const mergedHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  if (init?.headers) {
    const extra = init.headers instanceof Headers
      ? Object.fromEntries(init.headers.entries())
      : (init.headers as Record<string, string>);
    Object.assign(mergedHeaders, extra);
  }
  const response = await fetch(url, { ...init, headers: mergedHeaders });

  if (!response.ok) {
    let detail: unknown;
    try {
      detail = await response.json();
    } catch {
      detail = await response.text();
    }
    const detailField =
      typeof detail === "object" && detail !== null && "detail" in detail
        ? (detail as Record<string, unknown>)["detail"]
        : undefined;
    const message =
      typeof detailField === "string"
        ? detailField
        : `HTTP ${String(response.status)} ${response.statusText}`;
    throw new ApiError({ status: response.status, message, detail });
  }

  if (response.status === 204) return undefined as unknown as T;
  return response.json() as Promise<T>;
}
