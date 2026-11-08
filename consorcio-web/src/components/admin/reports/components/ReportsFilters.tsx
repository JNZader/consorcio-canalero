import { Button, Group, Paper, Select, TextInput } from '@mantine/core';
import { CATEGORY_OPTIONS, STATUS_OPTIONS } from '../../../../constants';

/** Opciones combinadas sort:order del selector móvil "Ordenar". */
const SORT_OPTIONS = [
  { value: 'created_at:desc', label: 'Más recientes' },
  { value: 'created_at:asc', label: 'Más antiguas' },
  { value: 'estado:desc', label: 'Estado (Z-A)' },
  { value: 'estado:asc', label: 'Estado (A-Z)' },
  { value: 'tipo:desc', label: 'Categoría (Z-A)' },
  { value: 'tipo:asc', label: 'Categoría (A-Z)' },
];

export function ReportsFilters({
  searchInputValue,
  onSearchInputChange,
  filterStatus,
  setFilterStatus,
  filterCategory,
  setFilterCategory,
  sort,
  order,
  onSortChange,
  onRefresh,
}: Readonly<{
  searchInputValue: string;
  onSearchInputChange: (value: string) => void;
  filterStatus: string | null;
  setFilterStatus: (value: string | null) => void;
  filterCategory: string | null;
  setFilterCategory: (value: string | null) => void;
  sort: string;
  order: 'asc' | 'desc';
  onSortChange: (sort: string, order: 'asc' | 'desc') => void;
  onRefresh: () => void;
}>) {
  return (
    <Paper shadow="sm" p="md" radius="md" mb="md">
      <Group
        className="cc-bandeja-filters"
        role="search"
        aria-label="Filtros de búsqueda de denuncias"
      >
        <TextInput
          placeholder="Buscar..."
          value={searchInputValue}
          onChange={(e) => onSearchInputChange(e.target.value)}
          style={{ flex: 1 }}
          aria-label="Buscar denuncias por descripción o ubicación"
        />
        <Select
          placeholder="Estado"
          data={[{ value: '', label: 'Todos' }, ...STATUS_OPTIONS]}
          value={filterStatus}
          onChange={setFilterStatus}
          clearable
          w={150}
          aria-label="Filtrar por estado de la denuncia"
        />
        <Select
          placeholder="Categoría"
          data={[{ value: '', label: 'Todas' }, ...CATEGORY_OPTIONS]}
          value={filterCategory}
          onChange={setFilterCategory}
          clearable
          w={150}
          aria-label="Filtrar por categoría de la denuncia"
        />
        {/* En móvil la fila ya apila a columna full-width via
            `.cc-bandeja-filters` (pointer: coarse), así que este Select
            hereda el mismo layout sin wrappers extra. En escritorio la
            tabla ordena por encabezado; este select queda como affordance
            visible también ahí. */}
        <Select
          placeholder="Ordenar"
          data={SORT_OPTIONS}
          value={`${sort}:${order}`}
          onChange={(value) => {
            const [nextSort, nextOrder] = String(value ?? 'created_at:desc').split(':');
            onSortChange(nextSort, nextOrder === 'asc' ? 'asc' : 'desc');
          }}
          w={170}
          aria-label="Ordenar la lista de denuncias"
        />
        <Button variant="light" onClick={onRefresh} aria-label="Actualizar lista de denuncias">
          Actualizar
        </Button>
      </Group>
    </Paper>
  );
}
