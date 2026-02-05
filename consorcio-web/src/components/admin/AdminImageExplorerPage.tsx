import { lazy, Suspense } from 'react';
import AdminLayout from './AdminLayout';
import ProtectedRoute from './ProtectedRoute';
import { LoadingState } from '../ui';

// Lazy load the heavy component
const ImageExplorerPanel = lazy(() =>
  import('./images/ImageExplorerPanel').then((m) => ({ default: m.default }))
);

export default function AdminImageExplorerPage() {
  return (
    <ProtectedRoute allowedRoles={['admin', 'operador']}>
      <AdminLayout currentPath="/admin/images">
        <Suspense fallback={<LoadingState message="Cargando explorador de imagenes..." />}>
          <ImageExplorerPanel />
        </Suspense>
      </AdminLayout>
    </ProtectedRoute>
  );
}
