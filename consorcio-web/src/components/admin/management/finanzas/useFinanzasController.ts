import { useForm } from '@mantine/form';
import { useDisclosure } from '@mantine/hooks';
import { useCallback, useEffect, useState } from 'react';
import { API_URL, apiFetch, getAuthToken } from '../../../../lib/api';
import { logger } from '../../../../lib/logger';
import { showError, showSuccess } from '../../../../lib/notifications';
import { erroresUi, textoError } from '../../../../lib/userFacingError';
import { GASTO_CATEGORIES, INGRESO_CATEGORIES } from './constants';
import type { Balance, Gasto, Ingreso } from './finanzasTypes';
import { buildOptionData, normalizeArray } from './finanzasUtils';

function validateDescripcion(value: string) {
  return value.trim().length < 3 ? 'Descripción requerida' : null;
}

function validateMonto(value: number) {
  return value > 0 ? null : 'El monto debe ser mayor a 0';
}

function validateCategoria(value: string) {
  return value ? null : 'Categoría requerida';
}

const today = () => new Date().toISOString().split('T')[0];

export function useFinanzasController() {
  const [gastos, setGastos] = useState<Gasto[]>([]);
  const [ingresos, setIngresos] = useState<Ingreso[]>([]);
  const [balance, setBalance] = useState<Balance | null>(null);
  const [loading, setLoading] = useState(true);
  const [exportingSummaryPdf, setExportingSummaryPdf] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState<string | null>('balance');
  const [editingGasto, setEditingGasto] = useState<Gasto | null>(null);
  const [editingIngreso, setEditingIngreso] = useState<Ingreso | null>(null);
  const currentYear = new Date().getFullYear();

  const [gastoOpened, gastoModal] = useDisclosure(false);
  const [editGastoOpened, editGastoModal] = useDisclosure(false);
  const [ingresoOpened, ingresoModal] = useDisclosure(false);
  const [editIngresoOpened, editIngresoModal] = useDisclosure(false);

  const form = useForm({
    initialValues: { descripcion: '', monto: 0, categoria: '', fecha: today() },
    validate: {
      descripcion: validateDescripcion,
      monto: validateMonto,
      categoria: validateCategoria,
    },
  });

  const editCategoryForm = useForm<{
    categoria: string;
    descripcion?: string;
    monto?: number;
    fecha?: string;
  }>({
    initialValues: { categoria: '', descripcion: '', monto: 0, fecha: '' },
    validate: {
      categoria: validateCategoria,
      descripcion: (val) => (!val ? 'Descripción requerida' : validateDescripcion(val)),
      monto: (val) =>
        val === undefined || val <= 0 ? 'El monto debe ser mayor a 0' : validateMonto(val),
    },
  });

  const ingresoForm = useForm({
    initialValues: { descripcion: '', monto: 0, categoria: '', fecha: today() },
    validate: {
      descripcion: validateDescripcion,
      monto: validateMonto,
      categoria: validateCategoria,
    },
  });

  const editIngresoForm = useForm({
    initialValues: { descripcion: '', monto: 0, categoria: '', fecha: '' },
    validate: {
      descripcion: validateDescripcion,
      monto: validateMonto,
      categoria: validateCategoria,
    },
  });

  const fetchFinanzas = useCallback(async () => {
    setLoading(true);
    try {
      const [gastosRaw, ingresosRaw, balanceData] = await Promise.all([
        apiFetch<Gasto[] | { items: Gasto[] }>('/finanzas/gastos'),
        apiFetch<Ingreso[] | { items: Ingreso[] }>('/finanzas/ingresos'),
        apiFetch<Balance>(`/finanzas/resumen/${currentYear}`),
      ]);
      setGastos(normalizeArray(gastosRaw));
      setIngresos(normalizeArray(ingresosRaw));
      setBalance(balanceData);
    } catch (error) {
      logger.error('Error fetching finanzas:', error);
    } finally {
      setLoading(false);
    }
  }, [currentYear]);

  useEffect(() => {
    fetchFinanzas();
  }, [fetchFinanzas]);

  const handleCreateGasto = async (values: typeof form.values) => {
    setSubmitting(true);
    try {
      await apiFetch('/finanzas/gastos', { method: 'POST', body: JSON.stringify(values) });
      gastoModal.close();
      form.reset();
      await fetchFinanzas();
      showSuccess('Gasto registrado', 'El gasto fue guardado correctamente');
    } catch (error) {
      logger.error('Error creating gasto:', error);
      showError(
        'No se pudo registrar el gasto',
        error instanceof Error ? error.message : 'Intentá nuevamente en unos minutos.'
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleOpenEditCategory = (gasto: Gasto) => {
    setEditingGasto(gasto);
    editCategoryForm.setValues({
      categoria: gasto.categoria,
      descripcion: gasto.descripcion,
      monto: gasto.monto,
      fecha: gasto.fecha,
    });
    editGastoModal.open();
  };

  const handleUpdateCategory = async (values: typeof editCategoryForm.values) => {
    if (!editingGasto) return;
    setSubmitting(true);
    try {
      const payload: Record<string, unknown> = { categoria: values.categoria };
      if (values.descripcion !== undefined && values.descripcion !== editingGasto.descripcion) {
        payload.descripcion = values.descripcion;
      }
      if (values.monto !== undefined && values.monto !== editingGasto.monto) {
        payload.monto = values.monto;
      }
      if (values.fecha !== undefined && values.fecha !== editingGasto.fecha) {
        payload.fecha = values.fecha;
      }

      await apiFetch(`/finanzas/gastos/${editingGasto.id}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      });
      editGastoModal.close();
      setEditingGasto(null);
      await fetchFinanzas();
      showSuccess('Categoría actualizada', 'La categoría del gasto fue actualizada');
    } catch (error) {
      logger.error('Error updating category:', error);
      showError(
        'No se pudo actualizar la categoría',
        error instanceof Error ? error.message : 'Intentá nuevamente en unos minutos.'
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleCreateIngreso = async (values: typeof ingresoForm.values) => {
    setSubmitting(true);
    try {
      await apiFetch('/finanzas/ingresos', { method: 'POST', body: JSON.stringify(values) });
      ingresoModal.close();
      ingresoForm.reset();
      await fetchFinanzas();
      showSuccess('Ingreso registrado', 'El ingreso fue guardado correctamente');
    } catch (error) {
      logger.error('Error creating ingreso:', error);
      showError(
        'No se pudo registrar el ingreso',
        error instanceof Error ? error.message : 'Intentá nuevamente en unos minutos.'
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleOpenEditIngreso = (ingreso: Ingreso) => {
    setEditingIngreso(ingreso);
    editIngresoForm.setValues({
      descripcion: ingreso.descripcion,
      monto: ingreso.monto,
      categoria: ingreso.categoria,
      fecha: ingreso.fecha,
    });
    editIngresoModal.open();
  };

  const handleUpdateIngreso = async (values: typeof editIngresoForm.values) => {
    if (!editingIngreso) return;
    setSubmitting(true);
    try {
      await apiFetch(`/finanzas/ingresos/${editingIngreso.id}`, {
        method: 'PATCH',
        body: JSON.stringify(values),
      });
      editIngresoModal.close();
      setEditingIngreso(null);
      await fetchFinanzas();
      showSuccess('Ingreso actualizado', 'Los datos del ingreso fueron actualizados');
    } catch (error) {
      logger.error('Error updating ingreso:', error);
      showError(
        'No se pudo actualizar el ingreso',
        error instanceof Error ? error.message : 'Intentá nuevamente en unos minutos.'
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleDownloadSummaryPdf = async () => {
    setExportingSummaryPdf(true);
    try {
      const token = await getAuthToken();
      const response = await fetch(`${API_URL}/api/v2/finanzas/resumen/${currentYear}/export-pdf`, {
        headers: {
          Accept: 'application/pdf',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
      if (!response.ok) {
        throw new Error(textoError(erroresUi.descargarResumen, `Respuesta ${response.status}.`));
      }
      const contentType = response.headers.get('content-type') ?? '';
      if (!contentType.includes('application/pdf')) {
        throw new Error(textoError(erroresUi.pdfInvalido));
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `resumen_financiero_${currentYear}.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      setTimeout(() => window.URL.revokeObjectURL(url), 1000);
    } catch (error) {
      logger.error('Error downloading financial summary PDF:', error);
      showError(
        'No se pudo descargar el resumen',
        error instanceof Error ? error.message : 'Intentá nuevamente en unos minutos.'
      );
    } finally {
      setExportingSummaryPdf(false);
    }
  };

  return {
    gastos,
    ingresos,
    balance,
    loading,
    activeTab,
    setActiveTab,
    editingIngreso,
    categoryData: buildOptionData([...GASTO_CATEGORIES]),
    ingresoCategoryData: buildOptionData([...INGRESO_CATEGORIES]),
    currentYear,
    exportingSummaryPdf,
    submitting,
    gastoOpened,
    editGastoOpened,
    ingresoOpened,
    editIngresoOpened,
    gastoModal,
    editGastoModal,
    ingresoModal,
    editIngresoModal,
    form,
    editCategoryForm,
    ingresoForm,
    editIngresoForm,
    handleCreateGasto,
    handleOpenEditCategory,
    handleUpdateCategory,
    handleCreateIngreso,
    handleOpenEditIngreso,
    handleUpdateIngreso,
    handleDownloadSummaryPdf,
  };
}
