import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

export function middleware(request: NextRequest) {
  const token = request.cookies.get("perceptai_token")?.value
  const isDashboard = request.nextUrl.pathname.startsWith("/dashboard")
  const isAuth = request.nextUrl.pathname.startsWith("/signin") || 
                 request.nextUrl.pathname.startsWith("/signup")
  const tokenValid = token ? isJwtValid(token) : false

  if (isDashboard && !tokenValid) {
    const res = NextResponse.redirect(new URL("/signin", request.url))
    if (token) {
      res.cookies.set("perceptai_token", "", { maxAge: 0, path: "/" })
    }
    return res
  }
  if (isAuth && tokenValid) {
    return NextResponse.redirect(new URL("/dashboard", request.url))
  }
  return NextResponse.next()
}

function isJwtValid(token: string): boolean {
  const parts = token.split(".")
  if (parts.length < 2) return false
  try {
    const payload = parts[1]
      .replace(/-/g, "+")
      .replace(/_/g, "/")
      .padEnd(Math.ceil(parts[1].length / 4) * 4, "=")
    const json = atob(payload)
    const data = JSON.parse(json) as { exp?: number }
    if (!data.exp) return true
    return Date.now() < data.exp * 1000
  } catch {
    return false
  }
}

export const config = {
  matcher: ["/dashboard/:path*", "/signin", "/signup"],
}