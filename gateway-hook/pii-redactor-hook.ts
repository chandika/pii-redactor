/**
 * OpenClaw Gateway PII Redactor Hook
 *
 * Integrates pii-redactor as a sidecar service that the gateway
 * calls via HTTP on localhost:18791.
 *
 * The sidecar runs: /opt/pii-redactor/bin/python -m pii_redactor.server
 *
 * This module provides:
 * 1. Functions to redact/rehydrate via the sidecar
 * 2. A helper to start the sidecar as a child process
 * 3. Integration with OpenClaw's hook system (when modifying hooks land)
 */

import { spawn, type ChildProcess } from "node:child_process";

const SIDECAR_URL =
  process.env.PII_REDACTOR_URL || "http://127.0.0.1:18791";
const PYTHON =
  (process.env.PII_REDACTOR_VENV || "/opt/pii-redactor") + "/bin/python";

// ─── Sidecar management ───────────────────────────────────────────

let sidecarProcess: ChildProcess | null = null;

export function startSidecar(opts?: {
  port?: number;
  dbPath?: string;
}): ChildProcess {
  if (sidecarProcess && !sidecarProcess.killed) {
    return sidecarProcess;
  }

  const args = ["-m", "pii_redactor.server"];
  if (opts?.port) args.push("--port", String(opts.port));
  if (opts?.dbPath) args.push("--db", opts.dbPath);

  sidecarProcess = spawn(PYTHON, args, {
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env },
  });

  sidecarProcess.stdout?.on("data", (chunk: Buffer) => {
    console.log(`[pii-redactor] ${chunk.toString().trim()}`);
  });

  sidecarProcess.stderr?.on("data", (chunk: Buffer) => {
    console.error(`[pii-redactor] ${chunk.toString().trim()}`);
  });

  sidecarProcess.on("exit", (code) => {
    console.log(`[pii-redactor] sidecar exited with code ${code}`);
    sidecarProcess = null;
  });

  return sidecarProcess;
}

export function stopSidecar(): void {
  if (sidecarProcess && !sidecarProcess.killed) {
    sidecarProcess.kill("SIGTERM");
    sidecarProcess = null;
  }
}

// ─── HTTP client ──────────────────────────────────────────────────

async function post<T>(
  path: string,
  body: Record<string, unknown>,
): Promise<T> {
  const res = await fetch(`${SIDECAR_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`pii-redactor ${path} failed (${res.status}): ${text}`);
  }
  return res.json() as Promise<T>;
}

// ─── Public API ───────────────────────────────────────────────────

export type ChatMessage = {
  role: string;
  content: string;
  [key: string]: unknown;
};

/**
 * Redact PII from OpenAI-format messages before sending to provider.
 */
export async function redactMessages(
  messages: ChatMessage[],
  sessionId: string,
): Promise<ChatMessage[]> {
  const result = await post<{ messages: ChatMessage[] }>("/redact", {
    session_id: sessionId,
    messages,
  });
  return result.messages;
}

/**
 * Redact PII from a single text string.
 */
export async function redactText(
  text: string,
  sessionId: string,
): Promise<{ text: string; entities: unknown[]; token_count: number }> {
  return post("/redact-text", { session_id: sessionId, text });
}

/**
 * Rehydrate tokens in provider response back to original PII values.
 */
export async function rehydrateText(
  text: string,
  sessionId: string,
): Promise<string> {
  const result = await post<{ text: string }>("/rehydrate", {
    session_id: sessionId,
    text,
  });
  return result.text;
}

/**
 * Check if the sidecar is running.
 */
export async function healthCheck(): Promise<boolean> {
  try {
    const res = await fetch(`${SIDECAR_URL}/health`);
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Clear vault for a session.
 */
export async function clearSession(sessionId: string): Promise<void> {
  await post("/clear", { session_id: sessionId });
}
