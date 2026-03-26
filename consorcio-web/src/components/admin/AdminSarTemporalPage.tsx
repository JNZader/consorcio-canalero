import AdminLayout from './AdminLayout';
import ProtectedRoute from './ProtectedRoute';
import SarTemporalPanel from './SarTemporalPanel';

export default function AdminSarTemporalPage() {
  return (
    <ProtectedRoute allowedRoles={['admin', 'operador']}>
      <AdminLayout currentPath="/admin/sar-temporal">
        <SarTemporalPanel />
      </AdminLayout>
    </ProtectedRoute>
  );
}
