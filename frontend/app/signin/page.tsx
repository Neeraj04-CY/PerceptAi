"use client"
import { useState } from "react"
import { useRouter } from "next/navigation"
import { signIn } from "@/lib/api"
import { saveToken } from "@/lib/auth"

export default function SignInPage() {
  const router = useRouter()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError("")
    try {
      const data = await signIn(email, password)
      saveToken(data.access_token)
      document.cookie = `perceptai_token=${data.access_token}; path=/`
      router.push("/dashboard")
    } catch (err: any) {
      setError(err.message || "Invalid credentials")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#050505] flex items-center justify-center">
      <div className="w-full max-w-md px-8">
        <div className="flex items-center gap-3 mb-12">
          <div className="w-8 h-8 bg-[#00FF85] rounded-sm flex items-center justify-center">
            <span className="text-black font-bold text-sm">P</span>
          </div>
          <span className="text-white font-bold text-xl tracking-wider">
            PERCEPTAI
          </span>
        </div>

        <h1 className="text-white text-3xl font-bold mb-2">Welcome back</h1>
        <p className="text-[#888] mb-8">Sign in to your account</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-[#888] text-sm block mb-2">Email</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              className="w-full bg-[#0D0D0D] border border-white/10 rounded-lg 
                px-4 py-3 text-white placeholder-[#555] focus:outline-none 
                focus:border-[#00FF85]/50 focus:ring-1 focus:ring-[#00FF85]/20
                transition-all"
            />
          </div>
          <div>
            <label className="text-[#888] text-sm block mb-2">Password</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              className="w-full bg-[#0D0D0D] border border-white/10 rounded-lg 
                px-4 py-3 text-white placeholder-[#555] focus:outline-none 
                focus:border-[#00FF85]/50 focus:ring-1 focus:ring-[#00FF85]/20
                transition-all"
            />
          </div>

          {error && (
            <p className="text-[#FF3B3B] text-sm bg-[#FF3B3B]/10 
              border border-[#FF3B3B]/20 rounded-lg px-4 py-3">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-[#00FF85] hover:bg-[#00e876] text-black 
              font-semibold py-3 rounded-lg transition-all
              disabled:opacity-50 disabled:cursor-not-allowed
              font-mono text-sm tracking-wider"
          >
            {loading ? "Signing in..." : "Sign In →"}
          </button>
        </form>

        <p className="text-[#555] text-sm mt-6 text-center">
          No account?{" "}
          <a href="/signup" className="text-[#00FF85] hover:underline">
            Create one
          </a>
        </p>
      </div>
    </div>
  )
}