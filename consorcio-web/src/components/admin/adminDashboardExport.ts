export interface DashboardJsonExport {
  blob: Blob;
  filename: string;
}

export function createDashboardJsonExport(
  payload: unknown,
  date: Date = new Date()
): DashboardJsonExport {
  return {
    blob: new Blob([JSON.stringify(payload, null, 2)], {
      type: 'application/json',
    }),
    filename: `datos_dashboard_${date.toISOString().slice(0, 10)}.json`,
  };
}
