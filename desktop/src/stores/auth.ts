import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthUser {
  id: string;
  username: string;
}

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  user: AuthUser | null;
  setTokens: (access: string, refresh: string, user: AuthUser) => void;
  setAccessToken: (access: string, refresh: string) => void;
  setUser: (user: AuthUser) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      refreshToken: null,
      user: null,
      setTokens: (access, refresh, user) =>
        set({ token: access, refreshToken: refresh, user }),
      setAccessToken: (access, refresh) =>
        set({ token: access, refreshToken: refresh }),
      setUser: (user) => set({ user }),
      logout: () => set({ token: null, refreshToken: null, user: null }),
    }),
    { name: "auth-storage" },
  ),
);