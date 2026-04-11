import { Badge } from '@mantine/core';
import { CATEGORY_OPTIONS, STATUS_OPTIONS } from '../../../constants';
import type { Report } from '../../../lib/api';

export function getStatusBadge(status: string): React.ReactNode {
  const option = STATUS_OPTIONS.find((o) => o.value === status);
  return (
    <Badge color={option?.color || 'gray'} variant="light">
      {option?.label || status}
    </Badge>
  );
}

export function getCategoryLabel(category: string): string {
  return CATEGORY_OPTIONS.find((c) => c.value === category)?.label || category;
}

export function filterReports(reports: Report[], filterCategory: string | null, searchQuery: string) {
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

  return { filteredReports, pendingCount: pending, inReviewCount: inReview };
}
