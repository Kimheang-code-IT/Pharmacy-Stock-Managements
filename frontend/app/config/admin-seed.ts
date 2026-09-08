/** Shared record type for module list/detail views and API entity payloads. */

export type AppRecord = Record<string, unknown> & { id: string }
