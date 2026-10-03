import { create } from 'zustand'

export const useAuthStore = create((set) => ({
  session: null,
  user: null,
  setSession: (session) => set({ session, user: session?.user ?? null }),
  clearSession: () => set({ session: null, user: null }),
}))
