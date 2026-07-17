/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { useRuntime, type RuntimeAuthConfig } from "./runtime";

const TOKEN_KEY = "atlas:access-token";
const TOKEN_EXPIRY_KEY = "atlas:access-token-expiry";
const VERIFIER_KEY = "atlas:pkce-verifier";
const STATE_KEY = "atlas:oauth-state";

interface AuthValue {
  accessToken: string | null;
  configured: boolean;
  signIn: () => Promise<void>;
  signOut: () => void;
  completeCallback: (code: string, state: string) => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

function authConfiguration(runtime: RuntimeAuthConfig | null) {
  return {
    domain:
      runtime?.domain ??
      (import.meta.env.VITE_COGNITO_DOMAIN as string | undefined)?.replace(/\/$/, ""),
    clientId: runtime?.clientId ?? (import.meta.env.VITE_COGNITO_CLIENT_ID as string | undefined),
    scope: (import.meta.env.VITE_COGNITO_SCOPE as string | undefined) ?? "openid profile email",
  };
}

function base64Url(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes))
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replaceAll("=", "");
}

function randomValue(length = 64): string {
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  return base64Url(bytes);
}

function callbackUrl(): string {
  return `${window.location.origin}/auth/callback`;
}

function storedToken(): string | null {
  const token = sessionStorage.getItem(TOKEN_KEY);
  const expiry = Number(sessionStorage.getItem(TOKEN_EXPIRY_KEY) ?? "0");
  if (!token || !expiry || Date.now() >= expiry - 30_000) {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(TOKEN_EXPIRY_KEY);
    return null;
  }
  return token;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(() => storedToken());
  const { authConfig } = useRuntime();
  const config = authConfiguration(authConfig);
  const configured = Boolean(config.domain && config.clientId);

  const signIn = useCallback(async () => {
    if (!config.domain || !config.clientId) throw new Error("Cognito login is not configured");
    const verifier = randomValue();
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
    const state = randomValue(24);
    sessionStorage.setItem(VERIFIER_KEY, verifier);
    sessionStorage.setItem(STATE_KEY, state);
    const params = new URLSearchParams({
      client_id: config.clientId,
      response_type: "code",
      redirect_uri: callbackUrl(),
      scope: config.scope,
      state,
      code_challenge_method: "S256",
      code_challenge: base64Url(new Uint8Array(digest)),
    });
    window.location.assign(`${config.domain}/oauth2/authorize?${params}`);
  }, [config.clientId, config.domain, config.scope]);

  const signOut = useCallback(() => {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(TOKEN_EXPIRY_KEY);
    setAccessToken(null);
  }, []);

  const completeCallback = useCallback(
    async (code: string, state: string) => {
      if (!config.domain || !config.clientId) throw new Error("Cognito login is not configured");
      const expectedState = sessionStorage.getItem(STATE_KEY);
      const verifier = sessionStorage.getItem(VERIFIER_KEY);
      if (!expectedState || state !== expectedState || !verifier) {
        throw new Error("The login response could not be verified");
      }
      const response = await fetch(`${config.domain}/oauth2/token`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          grant_type: "authorization_code",
          client_id: config.clientId,
          code,
          redirect_uri: callbackUrl(),
          code_verifier: verifier,
        }),
      });
      if (!response.ok) throw new Error("Cognito rejected the authorization code");
      const tokens = (await response.json()) as {
        access_token?: string;
        id_token?: string;
        expires_in?: number;
      };
      const bearerToken = tokens.id_token ?? tokens.access_token;
      if (!bearerToken) throw new Error("Cognito did not return a bearer token");
      const expiry = Date.now() + (tokens.expires_in ?? 3600) * 1000;
      sessionStorage.setItem(TOKEN_KEY, bearerToken);
      sessionStorage.setItem(TOKEN_EXPIRY_KEY, String(expiry));
      sessionStorage.removeItem(STATE_KEY);
      sessionStorage.removeItem(VERIFIER_KEY);
      setAccessToken(bearerToken);
    },
    [config.clientId, config.domain],
  );

  const value = useMemo(
    () => ({ accessToken, configured, signIn, signOut, completeCallback }),
    [accessToken, configured, signIn, signOut, completeCallback],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}

export function getStoredAccessToken(): string | null {
  return storedToken();
}
