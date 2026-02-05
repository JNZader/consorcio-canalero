import AdminDashboard from './AdminDashboard';
import AdminLayout from './AdminLayout';
import ProtectedRoute from './ProtectedRoute';

export default function AdminDashboardPage() {
  return (
    <ProtectedRoute allowedRoles={['admin', 'operador']}>
      <AdminLayout currentPath="/admin">
        <AdminDashboard />
      </AdminLayout>
    </ProtectedRoute>
  );
}
