import AdminLayout from './AdminLayout';
import ProtectedRoute from './ProtectedRoute';
import SugerenciasPanel from './sugerencias/SugerenciasPanel';

export default function AdminSugerenciasPage() {
  return (
    <ProtectedRoute allowedRoles={['admin', 'operador']}>
      <AdminLayout currentPath="/admin/sugerencias">
        <SugerenciasPanel />
      </AdminLayout>
    </ProtectedRoute>
  );
}
