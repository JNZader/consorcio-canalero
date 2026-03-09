/**
 * admin-pages.test.tsx
 * Unit: Admin page wrapper components (AdminDashboardPage, AdminReportsPage, AdminSugerenciasPage)
 * Coverage Target: 100% for all three page wrappers
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import AdminDashboardPage from '../../src/components/admin/AdminDashboardPage';
import AdminReportsPage from '../../src/components/admin/AdminReportsPage';
import AdminSugerenciasPage from '../../src/components/admin/AdminSugerenciasPage';

// Mock the child components
vi.mock('../../src/components/admin/AdminDashboard', () => ({
  default: () => <div data-testid="admin-dashboard">Admin Dashboard</div>,
}));

vi.mock('../../src/components/admin/AdminLayout', () => ({
  default: ({ children, currentPath }: any) => (
    <div data-testid="admin-layout" data-path={currentPath}>
      {children}
    </div>
  ),
}));

vi.mock('../../src/components/admin/ProtectedRoute', () => ({
  default: ({ children, allowedRoles }: any) => (
    <div data-testid="protected-route" data-roles={JSON.stringify(allowedRoles)}>
      {children}
    </div>
  ),
}));

vi.mock('../../src/components/admin/reports/ReportsPanel', () => ({
  default: () => <div data-testid="reports-panel">Reports Panel</div>,
}));

vi.mock('../../src/components/admin/sugerencias/SugerenciasPanel', () => ({
  default: () => <div data-testid="sugerencias-panel">Sugerencias Panel</div>,
}));

const Wrapper = ({ children }: { children: React.ReactNode }) => (
  <div>{children}</div>
);

describe('Admin Page Wrappers', () => {
  describe('AdminDashboardPage', () => {
    it('should render without crashing', () => {
      render(<AdminDashboardPage />, { wrapper: Wrapper });
      expect(screen.getByTestId('protected-route')).toBeInTheDocument();
    });

    it('should wrap content in ProtectedRoute', () => {
      render(<AdminDashboardPage />, { wrapper: Wrapper });
      const protectedRoute = screen.getByTestId('protected-route');
      expect(protectedRoute).toBeInTheDocument();
    });

    it('should allow admin and operador roles', () => {
      render(<AdminDashboardPage />, { wrapper: Wrapper });
      const protectedRoute = screen.getByTestId('protected-route');
      const roles = JSON.parse(protectedRoute.getAttribute('data-roles') || '[]');
      expect(roles).toContain('admin');
      expect(roles).toContain('operador');
    });

    it('should have exactly 2 allowed roles', () => {
      render(<AdminDashboardPage />, { wrapper: Wrapper });
      const protectedRoute = screen.getByTestId('protected-route');
      const roles = JSON.parse(protectedRoute.getAttribute('data-roles') || '[]');
      expect(roles).toHaveLength(2);
    });

    it('should wrap layout in AdminLayout', () => {
      render(<AdminDashboardPage />, { wrapper: Wrapper });
      expect(screen.getByTestId('admin-layout')).toBeInTheDocument();
    });

    it('should set correct currentPath for AdminLayout', () => {
      render(<AdminDashboardPage />, { wrapper: Wrapper });
      const layout = screen.getByTestId('admin-layout');
      expect(layout.getAttribute('data-path')).toBe('/admin');
    });

    it('should render AdminDashboard inside layout', () => {
      render(<AdminDashboardPage />, { wrapper: Wrapper });
      expect(screen.getByTestId('admin-dashboard')).toBeInTheDocument();
    });

    it('should have AdminDashboard as a child of AdminLayout', () => {
      render(<AdminDashboardPage />, { wrapper: Wrapper });
      const layout = screen.getByTestId('admin-layout');
      const dashboard = screen.getByTestId('admin-dashboard');
      expect(layout).toContainElement(dashboard);
    });

    it('should maintain proper component hierarchy', () => {
      render(<AdminDashboardPage />, { wrapper: Wrapper });
      const protectedRoute = screen.getByTestId('protected-route');
      const layout = screen.getByTestId('admin-layout');
      const dashboard = screen.getByTestId('admin-dashboard');

      expect(protectedRoute).toContainElement(layout);
      expect(layout).toContainElement(dashboard);
    });
  });

  describe('AdminReportsPage', () => {
    it('should render without crashing', () => {
      render(<AdminReportsPage />, { wrapper: Wrapper });
      expect(screen.getByTestId('protected-route')).toBeInTheDocument();
    });

    it('should wrap content in ProtectedRoute', () => {
      render(<AdminReportsPage />, { wrapper: Wrapper });
      const protectedRoute = screen.getByTestId('protected-route');
      expect(protectedRoute).toBeInTheDocument();
    });

    it('should allow admin and operador roles', () => {
      render(<AdminReportsPage />, { wrapper: Wrapper });
      const protectedRoute = screen.getByTestId('protected-route');
      const roles = JSON.parse(protectedRoute.getAttribute('data-roles') || '[]');
      expect(roles).toContain('admin');
      expect(roles).toContain('operador');
    });

    it('should have exactly 2 allowed roles', () => {
      render(<AdminReportsPage />, { wrapper: Wrapper });
      const protectedRoute = screen.getByTestId('protected-route');
      const roles = JSON.parse(protectedRoute.getAttribute('data-roles') || '[]');
      expect(roles).toHaveLength(2);
    });

    it('should wrap layout in AdminLayout', () => {
      render(<AdminReportsPage />, { wrapper: Wrapper });
      expect(screen.getByTestId('admin-layout')).toBeInTheDocument();
    });

    it('should set correct currentPath for AdminLayout', () => {
      render(<AdminReportsPage />, { wrapper: Wrapper });
      const layout = screen.getByTestId('admin-layout');
      expect(layout.getAttribute('data-path')).toBe('/admin/reports');
    });

    it('should render ReportsPanel inside layout', () => {
      render(<AdminReportsPage />, { wrapper: Wrapper });
      expect(screen.getByTestId('reports-panel')).toBeInTheDocument();
    });

    it('should have ReportsPanel as a child of AdminLayout', () => {
      render(<AdminReportsPage />, { wrapper: Wrapper });
      const layout = screen.getByTestId('admin-layout');
      const panel = screen.getByTestId('reports-panel');
      expect(layout).toContainElement(panel);
    });

    it('should maintain proper component hierarchy', () => {
      render(<AdminReportsPage />, { wrapper: Wrapper });
      const protectedRoute = screen.getByTestId('protected-route');
      const layout = screen.getByTestId('admin-layout');
      const panel = screen.getByTestId('reports-panel');

      expect(protectedRoute).toContainElement(layout);
      expect(layout).toContainElement(panel);
    });

    it('should have different path than AdminDashboardPage', () => {
      const { unmount: unmount1 } = render(<AdminDashboardPage />, {
        wrapper: Wrapper,
      });
      const dashboardLayout = screen.getByTestId('admin-layout');
      const dashboardPath = dashboardLayout.getAttribute('data-path');

      unmount1();

      render(<AdminReportsPage />, { wrapper: Wrapper });
      const reportsLayout = screen.getByTestId('admin-layout');
      const reportsPath = reportsLayout.getAttribute('data-path');

      expect(dashboardPath).not.toBe(reportsPath);
    });
  });

  describe('AdminSugerenciasPage', () => {
    it('should render without crashing', () => {
      render(<AdminSugerenciasPage />, { wrapper: Wrapper });
      expect(screen.getByTestId('protected-route')).toBeInTheDocument();
    });

    it('should wrap content in ProtectedRoute', () => {
      render(<AdminSugerenciasPage />, { wrapper: Wrapper });
      const protectedRoute = screen.getByTestId('protected-route');
      expect(protectedRoute).toBeInTheDocument();
    });

    it('should allow admin and operador roles', () => {
      render(<AdminSugerenciasPage />, { wrapper: Wrapper });
      const protectedRoute = screen.getByTestId('protected-route');
      const roles = JSON.parse(protectedRoute.getAttribute('data-roles') || '[]');
      expect(roles).toContain('admin');
      expect(roles).toContain('operador');
    });

    it('should have exactly 2 allowed roles', () => {
      render(<AdminSugerenciasPage />, { wrapper: Wrapper });
      const protectedRoute = screen.getByTestId('protected-route');
      const roles = JSON.parse(protectedRoute.getAttribute('data-roles') || '[]');
      expect(roles).toHaveLength(2);
    });

    it('should wrap layout in AdminLayout', () => {
      render(<AdminSugerenciasPage />, { wrapper: Wrapper });
      expect(screen.getByTestId('admin-layout')).toBeInTheDocument();
    });

    it('should set correct currentPath for AdminLayout', () => {
      render(<AdminSugerenciasPage />, { wrapper: Wrapper });
      const layout = screen.getByTestId('admin-layout');
      expect(layout.getAttribute('data-path')).toBe('/admin/sugerencias');
    });

    it('should render SugerenciasPanel inside layout', () => {
      render(<AdminSugerenciasPage />, { wrapper: Wrapper });
      expect(screen.getByTestId('sugerencias-panel')).toBeInTheDocument();
    });

    it('should have SugerenciasPanel as a child of AdminLayout', () => {
      render(<AdminSugerenciasPage />, { wrapper: Wrapper });
      const layout = screen.getByTestId('admin-layout');
      const panel = screen.getByTestId('sugerencias-panel');
      expect(layout).toContainElement(panel);
    });

    it('should maintain proper component hierarchy', () => {
      render(<AdminSugerenciasPage />, { wrapper: Wrapper });
      const protectedRoute = screen.getByTestId('protected-route');
      const layout = screen.getByTestId('admin-layout');
      const panel = screen.getByTestId('sugerencias-panel');

      expect(protectedRoute).toContainElement(layout);
      expect(layout).toContainElement(panel);
    });

    it('should have different path than other admin pages', () => {
      const { unmount: unmount1 } = render(<AdminReportsPage />, {
        wrapper: Wrapper,
      });
      const reportsLayout = screen.getByTestId('admin-layout');
      const reportsPath = reportsLayout.getAttribute('data-path');

      unmount1();

      render(<AdminSugerenciasPage />, { wrapper: Wrapper });
      const sugerenciasLayout = screen.getByTestId('admin-layout');
      const sugerenciasPath = sugerenciasLayout.getAttribute('data-path');

      expect(reportsPath).not.toBe(sugerenciasPath);
    });
  });

  describe('Shared patterns across admin pages', () => {
    it('all admin pages should require admin or operador role', () => {
      const pages = [
        <AdminDashboardPage />,
        <AdminReportsPage />,
        <AdminSugerenciasPage />,
      ];

      pages.forEach((page) => {
        const { unmount } = render(page, { wrapper: Wrapper });
        const protectedRoute = screen.getByTestId('protected-route');
        const roles = JSON.parse(
          protectedRoute.getAttribute('data-roles') || '[]'
        );

        expect(roles).toContain('admin');
        expect(roles).toContain('operador');
        expect(roles).toHaveLength(2);

        unmount();
      });
    });

    it('all admin pages should render inside AdminLayout', () => {
      const pages = [
        <AdminDashboardPage />,
        <AdminReportsPage />,
        <AdminSugerenciasPage />,
      ];

      pages.forEach((page) => {
        const { unmount } = render(page, { wrapper: Wrapper });
        expect(screen.getByTestId('admin-layout')).toBeInTheDocument();
        unmount();
      });
    });

    it('each admin page should have unique currentPath', () => {
      const paths: string[] = [];

      const pages = [
        { page: <AdminDashboardPage />, expectedPath: '/admin' },
        { page: <AdminReportsPage />, expectedPath: '/admin/reports' },
        {
          page: <AdminSugerenciasPage />,
          expectedPath: '/admin/sugerencias',
        },
      ];

      pages.forEach(({ page, expectedPath }) => {
        const { unmount } = render(page, { wrapper: Wrapper });
        const layout = screen.getByTestId('admin-layout');
        const path = layout.getAttribute('data-path');

        expect(path).toBe(expectedPath);
        paths.push(path!);

        unmount();
      });

      // Verify all paths are unique
      const uniquePaths = new Set(paths);
      expect(uniquePaths.size).toBe(paths.length);
    });
  });
});
