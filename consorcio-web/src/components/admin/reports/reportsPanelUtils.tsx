import { CATEGORY_OPTIONS } from '../../../constants';
import type { Report } from '../../../lib/api';
import { StatusBadge } from '../../ui/StatusBadge';

export function getStatusBadge(status: string): React.ReactNode {
  return <StatusBadge status={status} />;
}

export function getCategoryLabel(category: string): string {
  return CATEGORY_OPTIONS.find((c) => c.value === category)?.label || category;
}

export interface ReportStatusCounts {
  pendiente: number;
  en_revision: number;
}

/** Badge fallback from the rows already returned when `/denuncias/stats` is unavailable. */
export function countReportStatuses(reports: Report[]): ReportStatusCounts {
  let pendiente = 0;
  let en_revision = 0;
  for (const report of reports) {
    if (report.estado === 'pendiente') pendiente++;
    if (report.estado === 'en_revision') en_revision++;
  }
  return { pendiente, en_revision };
}
