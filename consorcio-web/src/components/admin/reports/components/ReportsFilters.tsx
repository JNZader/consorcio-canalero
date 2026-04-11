import { Button, Group, Paper, Select, TextInput } from '@mantine/core';
import { CATEGORY_OPTIONS, STATUS_OPTIONS } from '../../../../constants';

export function ReportsFilters({
  searchInputValue,
  onSearchInputChange,
  filterStatus,
  setFilterStatus,
  filterCategory,
  setFilterCategory,
  onRefresh,
}: Readonly<{
  searchInputValue: string;
  onSearchInputChange: (value: string) => void;
  filterStatus: string | null;
  setFilterStatus: (value: string | null) => void;
  filterCategory: string | null;
  setFilterCategory: (value: string | null) => void;
  onRefresh: () => void;
}>) {
  return (
    <Paper shadow="sm" p="md" radius="md" mb="md">
      <Group role="search" aria-label="Filtros de busqueda de denuncias">
        <TextInput
          placeholder="Buscar..."
          value={searchInputValue}
          onChange={(e) => onSearchInputChange(e.target.value)}
          style={{ flex: 1 }}
          aria-label="Buscar denuncias por descripcion o ubicacion"
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
          placeholder="Categoria"
          data={[{ value: '', label: 'Todas' }, ...CATEGORY_OPTIONS]}
          value={filterCategory}
          onChange={setFilterCategory}
          clearable
          w={150}
          aria-label="Filtrar por categoria de la denuncia"
        />
        <Button variant="light" onClick={onRefresh} aria-label="Actualizar lista de denuncias">
          Actualizar
        </Button>
      </Group>
    </Paper>
  );
}
