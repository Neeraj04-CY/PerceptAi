export function saveToken(token: string) {
  localStorage.setItem("perceptai_token", token)
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null
  return localStorage.getItem("perceptai_token")
}

export function clearToken() {
  localStorage.removeItem("perceptai_token")
}

export function isAuthenticated(): boolean {
  return !!getToken()
}