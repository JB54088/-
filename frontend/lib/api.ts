const API_URL = process.env.NEXT_PUBLIC_API_URL || "/api";

export function getToken() {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("customer_assets_token");
}

export function getStoredUser() {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem("customer_assets_user");
  return raw ? JSON.parse(raw) : null;
}

export function logout() {
  window.localStorage.removeItem("customer_assets_token");
  window.localStorage.removeItem("customer_assets_user");
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(options.headers);
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  if (!isFormData) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_URL}${path}`, { ...options, headers, cache: "no-store" });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    if (response.status === 401 && typeof window !== "undefined") logout();
    throw new Error(payload.detail || "请求失败，请稍后重试");
  }
  return response.json();
}

export { API_URL };
