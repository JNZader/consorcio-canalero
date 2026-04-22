import { useForm } from '@mantine/form';
import { useDisclosure } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../../../../lib/api';
import { logger } from '../../../../lib/logger';
import { DEFAULT_CATEGORIES, DEFAULT_INCOME_SOURCES } from './constants';
import type { Balance, Gasto, Ingreso } from './finanzasTypes';
import {
  addNormalizedOption,
  buildOptionData,
  getFinanzasOptions,
  normalizeArray,
} from './finanzasUtils';

export function useFinanzasController() {
  const [gastos, setGastos] = useState<Gasto[]>([]);
  const [ingresos, setIngresos] = useState<Ingreso[]>([]);
  const [balance, setBalance] = useState<Balance | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<string | null>('balance');
  const [categoryOptions, setCategoryOptions] = useState<string[]>([]);
  const [sourceOptions, setSourceOptions] = useState<string[]>([]);
  const [editingGasto, setEditingGasto] = useState<Gasto | null>(null);
  const [editingIngreso, setEditingIngreso] = useState<Ingreso | null>(null);
  const [newCategoryName, setNewCategoryName] = useState('');
  const [newSourceName, setNewSourceName] = useState('');
  const [gastoComprobanteFile, setGastoComprobanteFile] = useState<File | null>(null);
  const [gastoEditComprobanteFile, setGastoEditComprobanteFile] = useState<File | null>(null);
  const [ingresoComprobanteFile, setIngresoComprobanteFile] = useState<File | null>(null);
  const [ingresoEditComprobanteFile, setIngresoEditComprobanteFile] = useState<File | null>(null);
  const [uploadingComprobante, setUploadingComprobante] = useState(false);

  const [gastoOpened, gastoModal] = useDisclosure(false);
  const [editGastoOpened, editGastoModal] = useDisclosure(false);
  const [ingresoOpened, ingresoModal] = useDisclosure(false);
  const [editIngresoOpened, editIngresoModal] = useDisclosure(false);
  const [categoryOpened, categoryModal] = useDisclosure(false);
  const [sourceOpened, sourceModal] = useDisclosure(false);

  const form = useForm({
    initialValues: {
      descripcion: '',
      monto: 0,
      categoria: '',
      comprobante_url: '',
      fecha: new Date().toISOString().split('T')[0],
    },
  });

  const editCategoryForm = useForm({
    initialValues: {
      categoria: '',
    },
  });

  const ingresoForm = useForm({
    initialValues: {
      descripcion: '',
      monto: 0,
      fuente: '',
      pagador: '',
      comprobante_url: '',
      fecha: new Date().toISOString().split('T')[0],
    },
  });

  const editIngresoForm = useForm({
    initialValues: {
      descripcion: '',
      monto: 0,
      fuente: '',
      pagador: '',
      comprobante_url: '',
      fecha: '',
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
      const gastosData = normalizeArray(gastosRaw);
      const ingresosData = normalizeArray(ingresosRaw);
      const options = getFinanzasOptions(
        gastosData,
        ingresosData,
        DEFAULT_CATEGORIES,
        DEFAULT_INCOME_SOURCES
      );

      setGastos(gastosData);
      setIngresos(ingresosData);
      setBalance(balanceData);
      setCategoryOptions(options.categoryOptions);
      setSourceOptions(options.sourceOptions);
    } catch (err) {
      logger.error('Error fetching finanzas:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFinanzas();
  }, [fetchFinanzas]);

  const uploadComprobante = async (file: File, tipo: 'gasto' | 'ingreso'): Promise<string> => {
    setUploadingComprobante(true);
    try {
      const formData = new FormData();
      formData.append('tipo', tipo);
      formData.append('file', file);

      const result = await apiFetch<{ url: string }>('/finanzas/comprobantes/upload', {
        method: 'POST',
        body: formData,
      });
      return result.url;
    } finally {
      setUploadingComprobante(false);
    }
  };

  const handleAddCategory = () => {
    const result = addNormalizedOption(categoryOptions, newCategoryName);
    if (!result.normalized) return;

    if (result.changed) {
      setCategoryOptions(result.nextOptions);
    }

    if (gastoOpened) {
      form.setFieldValue('categoria', result.normalized);
    }
    if (editGastoOpened) {
      editCategoryForm.setFieldValue('categoria', result.normalized);
    }

    setNewCategoryName('');
    categoryModal.close();
  };

  const handleAddSource = () => {
    const result = addNormalizedOption(sourceOptions, newSourceName);
    if (!result.normalized) return;

    if (result.changed) {
      setSourceOptions(result.nextOptions);
    }

    ingresoForm.setFieldValue('fuente', result.normalized);
    if (editIngresoOpened) {
      editIngresoForm.setFieldValue('fuente', result.normalized);
    }

    setNewSourceName('');
    sourceModal.close();
  };

  const handleCreateGasto = async (values: typeof form.values) => {
    try {
      let comprobanteUrl = values.comprobante_url;
      if (gastoComprobanteFile) {
        comprobanteUrl = await uploadComprobante(gastoComprobanteFile, 'gasto');
      }

      await apiFetch('/finanzas/gastos', {
        method: 'POST',
        body: JSON.stringify({
          ...values,
          comprobante_url: comprobanteUrl || undefined,
        }),
      });
      gastoModal.close();
      form.reset();
      setGastoComprobanteFile(null);
      await fetchFinanzas();
      notifications.show({
        title: 'Gasto registrado',
        message: 'El gasto fue guardado correctamente',
        color: 'green',
      });
    } catch (err) {
      logger.error('Error creating gasto:', err);
    }
  };

  const handleOpenEditCategory = (gasto: Gasto) => {
    setEditingGasto(gasto);
    editCategoryForm.setFieldValue('categoria', gasto.categoria);
    setGastoEditComprobanteFile(null);
    editGastoModal.open();
  };

  const setEditingGastoComprobanteUrl = (comprobanteUrl: string) => {
    setEditingGasto((current) =>
      current
        ? {
            ...current,
            comprobante_url: comprobanteUrl,
          }
        : current
    );
  };

  const handleUpdateCategory = async (values: typeof editCategoryForm.values) => {
    if (!editingGasto) return;

    try {
      let comprobanteUrl = editingGasto.comprobante_url || '';
      if (gastoEditComprobanteFile) {
        comprobanteUrl = await uploadComprobante(gastoEditComprobanteFile, 'gasto');
      }

      await apiFetch(`/finanzas/gastos/${editingGasto.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          categoria: values.categoria,
          comprobante_url: comprobanteUrl || undefined,
        }),
      });
      editGastoModal.close();
      setEditingGasto(null);
      setGastoEditComprobanteFile(null);
      await fetchFinanzas();
      notifications.show({
        title: 'Categoria actualizada',
        message: 'La categoria del gasto fue actualizada',
        color: 'green',
      });
    } catch (err) {
      logger.error('Error updating category:', err);
    }
  };

  const handleCreateIngreso = async (values: typeof ingresoForm.values) => {
    try {
      let comprobanteUrl = values.comprobante_url;
      if (ingresoComprobanteFile) {
        comprobanteUrl = await uploadComprobante(ingresoComprobanteFile, 'ingreso');
      }

      await apiFetch('/finanzas/ingresos', {
        method: 'POST',
        body: JSON.stringify({
          ...values,
          comprobante_url: comprobanteUrl || undefined,
        }),
      });
      ingresoModal.close();
      ingresoForm.reset();
      setIngresoComprobanteFile(null);
      await fetchFinanzas();
      notifications.show({
        title: 'Ingreso registrado',
        message: 'El ingreso fue guardado correctamente',
        color: 'green',
      });
    } catch (err) {
      logger.error('Error creating ingreso:', err);
    }
  };

  const handleOpenEditIngreso = (ingreso: Ingreso) => {
    setEditingIngreso(ingreso);
    editIngresoForm.setValues({
      descripcion: ingreso.descripcion,
      monto: ingreso.monto,
      fuente: ingreso.fuente,
      pagador: ingreso.pagador || '',
      comprobante_url: ingreso.comprobante_url || '',
      fecha: ingreso.fecha,
    });
    setIngresoEditComprobanteFile(null);
    editIngresoModal.open();
  };

  const handleUpdateIngreso = async (values: typeof editIngresoForm.values) => {
    if (!editingIngreso) return;

    try {
      let comprobanteUrl = values.comprobante_url;
      if (ingresoEditComprobanteFile) {
        comprobanteUrl = await uploadComprobante(ingresoEditComprobanteFile, 'ingreso');
      }

      await apiFetch(`/finanzas/ingresos/${editingIngreso.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          ...values,
          comprobante_url: comprobanteUrl || undefined,
        }),
      });
      editIngresoModal.close();
      setEditingIngreso(null);
      setIngresoEditComprobanteFile(null);
      await fetchFinanzas();
      notifications.show({
        title: 'Ingreso actualizado',
        message: 'Los datos del ingreso fueron actualizados',
        color: 'green',
      });
    } catch (err) {
      logger.error('Error updating ingreso:', err);
    }
  };

  return {
    gastos,
    ingresos,
    balance,
    loading,
    activeTab,
    setActiveTab,
    editingGasto,
    editingIngreso,
    categoryData: buildOptionData(categoryOptions),
    sourceData: buildOptionData(sourceOptions),
    currentYear: new Date().getFullYear(),
    gastoOpened,
    editGastoOpened,
    ingresoOpened,
    editIngresoOpened,
    categoryOpened,
    sourceOpened,
    gastoModal,
    editGastoModal,
    ingresoModal,
    editIngresoModal,
    categoryModal,
    sourceModal,
    form,
    editCategoryForm,
    ingresoForm,
    editIngresoForm,
    newCategoryName,
    setNewCategoryName,
    newSourceName,
    setNewSourceName,
    gastoComprobanteFile,
    setGastoComprobanteFile,
    gastoEditComprobanteFile,
    setGastoEditComprobanteFile,
    ingresoComprobanteFile,
    setIngresoComprobanteFile,
    ingresoEditComprobanteFile,
    setIngresoEditComprobanteFile,
    uploadingComprobante,
    handleAddCategory,
    handleAddSource,
    handleCreateGasto,
    handleOpenEditCategory,
    setEditingGastoComprobanteUrl,
    handleUpdateCategory,
    handleCreateIngreso,
    handleOpenEditIngreso,
    handleUpdateIngreso,
  };
}
