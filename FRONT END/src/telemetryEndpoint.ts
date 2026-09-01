const configuredTelemetryOrigin =
  import.meta.env.VITE_IIOS_TELEMETRY_URL?.trim().replace(/\/$/, "") ?? "";

export function telemetryUrl(path: string): string {
  if (!path.startsWith("/")) {
    throw new Error("Telemetry paths must be absolute");
  }
  return configuredTelemetryOrigin ? `${configuredTelemetryOrigin}${path}` : path;
}

export const remoteTelemetryConfigured = configuredTelemetryOrigin.length > 0;
