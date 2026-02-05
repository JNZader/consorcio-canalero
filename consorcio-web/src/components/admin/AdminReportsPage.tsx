import AdminLayout from './AdminLayout';
import ProtectedRoute from './ProtectedRoute';
import ReportsPanel from './reports/ReportsPanel';

export default function AdminReportsPage() {
  return (
    <ProtectedRoute allowedRoles={['admin', 'operador']}>
      <AdminLayout currentPath="/admin/reports">
        <ReportsPanel />
      </AdminLayout>
    </ProtectedRoute>
  );
}
