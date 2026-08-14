import type { Trip, VerificationCheck } from '@/lib/types';

export const AGENT_TASKS = [
  'flightSearch',
  'staySearch',
  'placeDiscovery',
  'itineraryGenerate',
  'itineraryVerify',
] as const;

export type AgentTaskId = (typeof AGENT_TASKS)[number];

export type AgentTaskInput = {
  flightSearch: { trip: Trip };
  staySearch: { trip: Trip };
  placeDiscovery: { trip: Trip };
  itineraryGenerate: { trip: Trip };
  itineraryVerify: { trip: Trip };
};

export type AgentErrorCode =
  | 'network'
  | 'timeout'
  | 'no_results'
  | 'invalid_input'
  | 'rate_limit'
  | 'agent_failed'
  | 'aborted';

type AgentEventBase = { seq: number; at: number };

export type AgentEvent = AgentEventBase & (
  | { type: 'status'; text: string }
  | { type: 'thought'; id: string; text: string; done: boolean }
  | { type: 'tool_call'; id: string; name: string; label: string; args?: Record<string, unknown> }
  | { type: 'tool_result'; id: string; label: string; count?: number; ok: boolean; detail?: string }
  | { type: 'partial'; payload: unknown }
  | { type: 'check_update'; check: VerificationCheck }
  | { type: 'progress'; value: number }
  | { type: 'done'; payload: unknown; summary?: string }
  | { type: 'error'; code: AgentErrorCode; message: string; retryable: boolean }
);

export type AgentClientState = {
  status: string | null;
  thoughts: { id: string; text: string; done: boolean }[];
  toolCalls: {
    id: string;
    name: string;
    label: string;
    resultLabel?: string;
    count?: number;
    ok?: boolean;
  }[];
  progress: number;
};

export const isAgentTask = (value: string): value is AgentTaskId =>
  (AGENT_TASKS as readonly string[]).includes(value);
