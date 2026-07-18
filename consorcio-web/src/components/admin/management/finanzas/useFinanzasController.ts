import { useForm } from '@mantine/form';
import { useDisclosure } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../../../../lib/api';
import { logger } from '../../../../lib/logger';
import { GASTO_CATEGORIES, INGRESO_CATEGORIES } from './constants';
import type { Balance, Gasto, Ingreso } from './finanzasTypes';
import { buildOptionData, normalizeArray } from './finanzasUtils';

function validateDescripcion(value: string) {
  return value.trim().length < 3 ? 'Descripcion requerida' : null;
}

function validateMonto(value: number) {
  return value > 0 ? null : 'El monto debe ser mayor a 0';
}

function validateCategoria(value: string) {
  return value ? null : 'Categoria requerida';
}

const today = () => new Date().toISOString().split('T')[0];

export function useFinanzasController() {
  const [gastos, setGastos] = useState<Gasto[]>([]);
  const [ingresos, setIngresos] = useState<Ingreso[]>([]);
  const [balance, setBalance] = useState<Balance | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<string | null>('balance');
  const [editingGasto, setEditingGasto] = useState<Gasto | null>(null);
  const [editingIngreso, setEditingIngreso] = useState<Ingreso | null>(null);

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

  const editCategoryForm = useForm({
    initialValues: { categoria: '' },
    validate: { categoria: validateCategoria },
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
        apiFetch<Balance>(`/finanzas/resumen/${new Date().getFullYear()}`),
      ]);
      setGastos(normalizeArray(gastosRaw));
      setIngresos(normalizeArray(ingresosRaw));
      setBalance(balanceData);
    } catch (error) {
      logger.error('Error fetching finanzas:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFinanzas();
  }, [fetchFinanzas]);

  const handleCreateGasto = async (values: typeof form.values) => {
    try {
      await apiFetch('/finanzas/gastos', { method: 'POST', body: JSON.stringify(values) });
      gastoModal.close();
      form.reset();
      await fetchFinanzas();
      notifications.show({
        title: 'Gasto registrado',
        message: 'El gasto fue guardado correctamente',
        color: 'green',
      });
    } catch (error) {
      logger.error('Error creating gasto:', error);
    }
  };

  const handleOpenEditCategory = (gasto: Gasto) => {
    setEditingGasto(gasto);
    editCategoryForm.setFieldValue('categoria', gasto.categoria);
    editGastoModal.open();
  };

  const handleUpdateCategory = async (values: typeof editCategoryForm.values) => {
    if (!editingGasto) return;
    try {
      await apiFetch(`/finanzas/gastos/${editingGasto.id}`, {
        method: 'PATCH',
        body: JSON.stringify(values),
      });
      editGastoModal.close();
      setEditingGasto(null);
      await fetchFinanzas();
      notifications.show({
        title: 'Categoria actualizada',
        message: 'La categoria del gasto fue actualizada',
        color: 'green',
      });
    } catch (error) {
      logger.error('Error updating category:', error);
    }
  };

  const handleCreateIngreso = async (values: typeof ingresoForm.values) => {
    try {
      await apiFetch('/finanzas/ingresos', { method: 'POST', body: JSON.stringify(values) });
      ingresoModal.close();
      ingresoForm.reset();
      await fetchFinanzas();
      notifications.show({
        title: 'Ingreso registrado',
        message: 'El ingreso fue guardado correctamente',
        color: 'green',
      });
    } catch (error) {
      logger.error('Error creating ingreso:', error);
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
    try {
      await apiFetch(`/finanzas/ingresos/${editingIngreso.id}`, {
        method: 'PATCH',
        body: JSON.stringify(values),
      });
      editIngresoModal.close();
      setEditingIngreso(null);
      await fetchFinanzas();
      notifications.show({
        title: 'Ingreso actualizado',
        message: 'Los datos del ingreso fueron actualizados',
        color: 'green',
      });
    } catch (error) {
      logger.error('Error updating ingreso:', error);
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
    currentYear: new Date().getFullYear(),
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
  };
}
