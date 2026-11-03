import { Button, Group, Paper, Select, TextInput } from '@mantine/core';
import { ESTADO_OPTIONS } from '../constants';

export function SugerenciasFilters({
  searchInputValue,
  onSearchInputChange,
  filterEstado,
  setFilterEstado,
  filterTipo,
  setFilterTipo,
  onRefresh,
}: Readonly<{
  searchInputValue: string;
  onSearchInputChange: (value: string) => void;
  filterEstado: string | null;
  setFilterEstado: (value: string | null) => void;
  filterTipo: string | null;
  setFilterTipo: (value: string | null) => void;
  onRefresh: () => void;
}>) {
  return (
    <Paper shadow="sm" p="md" radius="md" mb="md">
      <Group role="search" aria-label="Filtros de búsqueda de sugerencias">
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
        <Button variant="light" onClick={onRefresh} aria-label="Actualizar lista de sugerencias">
          Actualizar
        </Button>
      </Group>
    </Paper>
  );
}
