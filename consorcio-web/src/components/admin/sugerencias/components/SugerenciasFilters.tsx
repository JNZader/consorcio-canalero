import { Button, Group, Paper, Select, TextInput } from '@mantine/core';
import { ESTADO_OPTIONS } from '../constants';

/** Opciones combinadas sort:order del selector móvil "Ordenar". */
const SORT_OPTIONS = [
  { value: 'created_at:desc', label: 'Más recientes' },
  { value: 'created_at:asc', label: 'Más antiguas' },
  { value: 'estado:desc', label: 'Estado (Z-A)' },
  { value: 'estado:asc', label: 'Estado (A-Z)' },
  { value: 'categoria:desc', label: 'Categoría (Z-A)' },
  { value: 'categoria:asc', label: 'Categoría (A-Z)' },
];

export function SugerenciasFilters({
  searchInputValue,
  onSearchInputChange,
  filterEstado,
  setFilterEstado,
  filterTipo,
  setFilterTipo,
  sort,
  order,
  onSortChange,
  onRefresh,
}: Readonly<{
  searchInputValue: string;
  onSearchInputChange: (value: string) => void;
  filterEstado: string | null;
  setFilterEstado: (value: string | null) => void;
  filterTipo: string | null;
  setFilterTipo: (value: string | null) => void;
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
        aria-label="Filtros de búsqueda de sugerencias"
      >
        <TextInput
          placeholder="Buscar..."
          value={searchInputValue}
          onChange={(e) => onSearchInputChange(e.target.value)}
          style={{ flex: 1 }}
          aria-label="Buscar sugerencias por título o descripción"
        />
        <Select
          placeholder="Estado"
          data={[{ value: '', label: 'Todos' }, ...ESTADO_OPTIONS]}
          value={filterEstado}
          onChange={setFilterEstado}
          clearable
          w={150}
          aria-label="Filtrar por estado de la sugerencia"
        />
        <Select
          placeholder="Tipo"
          data={[
            { value: '', label: 'Todos' },
            { value: 'ciudadana', label: 'Ciudadana' },
            { value: 'interna', label: 'Interna' },
          ]}
          value={filterTipo}
          onChange={setFilterTipo}
          clearable
          w={150}
          aria-label="Filtrar por tipo de sugerencia"
        />
        {/* En móvil la fila ya apila a columna full-width via
            `.cc-bandeja-filters` (pointer: coarse); este Select hereda
            el mismo layout sin wrappers extra. */}
        <Select
          placeholder="Ordenar"
          data={SORT_OPTIONS}
          value={`${sort}:${order}`}
          onChange={(value) => {
            const [nextSort, nextOrder] = String(value ?? 'created_at:desc').split(':');
            onSortChange(nextSort, nextOrder === 'asc' ? 'asc' : 'desc');
          }}
          w={170}
          aria-label="Ordenar la lista de sugerencias"
        />
        <Button variant="light" onClick={onRefresh} aria-label="Actualizar lista de sugerencias">
          Actualizar
        </Button>
      </Group>
    </Paper>
  );
}
