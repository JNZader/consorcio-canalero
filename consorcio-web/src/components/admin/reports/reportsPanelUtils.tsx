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

export function filterReports(
  reports: Report[],
  filterCategory: string | null,
  searchQuery: string,
  globalStats?: ReportStatusCounts | null
) {
  let pending = 0;
  let inReview = 0;

  const filteredReports = reports.filter((report) => {
    if (report.estado === 'pendiente') pending++;
    if (report.estado === 'en_revision') inReview++;
    if (filterCategory && report.categoria !== filterCategory) return false;
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return (
        report.descripcion.toLowerCase().includes(query) ||
        report.ubicacion_texto?.toLowerCase().includes(query)
      );
    }
    return true;
  });

  return {
    filteredReports,
    pendingCount: globalStats ? globalStats.pendiente : pending,
    inReviewCount: globalStats ? globalStats.en_revision : inReview,
  };
}
