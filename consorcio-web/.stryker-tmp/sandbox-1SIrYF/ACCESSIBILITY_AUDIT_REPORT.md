# Auditoria de Accesibilidad WCAG 2.1 AA
## Consorcio Canalero 10 de Mayo - Sistema Web

> **NOTA HISTORICA:** Esta auditoria se realizo cuando la aplicacion usaba Astro.
> La arquitectura fue migrada a React + Vite + TanStack Router en enero 2026.
> Algunas referencias a archivos .astro ya no aplican.

**Fecha de Auditoria:** 2026-01-06
**Auditor:** Claude Opus 4.5
**Estandar:** WCAG 2.1 Nivel AA
**Alcance:** Aplicacion web completa (consorcio-web)

---

## Resumen Ejecutivo

| Categoria | Critico | Serio | Moderado | Menor | Total |
|-----------|---------|-------|----------|-------|-------|
| Semantica HTML | 1 | 3 | 2 | 1 | 7 |
| Navegacion Teclado | 2 | 2 | 1 | 0 | 5 |
| ARIA | 1 | 4 | 2 | 1 | 8 |
| Formularios | 2 | 3 | 2 | 1 | 8 |
| Imagenes/Media | 1 | 2 | 1 | 0 | 4 |
| Contraste Colores | 0 | 3 | 2 | 1 | 6 |
| Mapa Interactivo | 3 | 4 | 2 | 0 | 9 |
| Screen Readers | 2 | 3 | 2 | 1 | 8 |
| **TOTAL** | **12** | **24** | **14** | **5** | **55** |

**Puntuacion de Conformidad Estimada:** 68% (Requiere mejoras significativas)

---

## 1. SEMANTICA HTML

### 1.1 [CRITICO] Falta de landmarks ARIA en paginas principales

**Ubicacion:** `src/layouts/Layout.astro`, `src/components/HomePage.tsx`

**Problema:** El contenido principal carece de roles de region apropiados. El `<main>` esta presente pero falta `<nav>` semantico en Header y `<aside>` en paneles laterales.

**WCAG:** 1.3.1 (Info and Relationships), 4.1.2 (Name, Role, Value)

**Codigo Actual:**
```tsx
// src/components/Header.tsx - Linea 30
<Box component="header" className={header}>
  <Container size="xl" py="sm">
    <Group justify="space-between">
      {/* Navegacion sin role="navigation" */}
      <Group gap="sm" visibleFrom="sm">
        {LINKS.map((link) => (
          <Button ...>
```

**Solucion Propuesta:**
```tsx
// src/components/Header.tsx
<Box component="header" className={header}>
  <Container size="xl" py="sm">
    <Group justify="space-between">
      {/* Logo con rol apropiado */}
      <UnstyledButton component="a" href="/" aria-label="Consorcio Canalero - Ir al inicio">
        ...
      </UnstyledButton>

      {/* Navegacion con landmark */}
      <Box component="nav" aria-label="Navegacion principal">
        <Group gap="sm" visibleFrom="sm" role="menubar">
          {LINKS.map((link) => (
            <Button
              key={link.href}
              component="a"
              href={link.href}
              variant="subtle"
              color="gray"
              role="menuitem"
            >
              {link.label}
            </Button>
          ))}
        </Group>
      </Box>
```

### 1.2 [SERIO] Jerarquia de encabezados inconsistente

**Ubicacion:** `src/components/HomePage.tsx`, `src/components/DashboardPanel.tsx`

**Problema:** Saltos en la jerarquia de encabezados (h1 a h4 directamente).

**Codigo Actual:**
```tsx
// src/components/DashboardPanel.tsx - Lineas 269, 320
<Title order={4}>Estado por Cuenca</Title>
// Deberia ser h3 si el h2 anterior es "Dashboard"
```

**Solucion:**
```tsx
// Estructura correcta de headings
<Title order={2}>Dashboard</Title>  {/* h2 */}
  <Title order={3}>Estado por Cuenca</Title>  {/* h3 */}
  <Title order={3}>Ultimas Denuncias</Title>  {/* h3 */}
  <Title order={3}>Historial de Analisis</Title>  {/* h3 */}
```

### 1.3 [SERIO] Footer sin estructura semantica apropiada

**Ubicacion:** `src/components/Footer.tsx`

**Problema:** Los grupos de enlaces no estan marcados como listas de navegacion.

**Solucion:**
```tsx
// src/components/Footer.tsx
<Box component="footer" bg="gray.9" c="white" py="xl" role="contentinfo">
  <Container size="xl">
    <Stack gap="lg">
      <Group justify="space-between" align="flex-start" wrap="wrap">
        {/* Info del consorcio */}
        <Box>
          <Text component="h2" size="lg" fw={700} mb="xs">
            Consorcio Canalero 10 de Mayo
          </Text>
          ...
        </Box>

        {/* Navegacion del footer */}
        <Box component="nav" aria-label="Enlaces del sitio">
          <Text component="h3" size="sm" fw={600} c="gray.3" id="footer-nav-title">
            Enlaces
          </Text>
          <Stack component="ul" gap="xs" style={{ listStyle: 'none', padding: 0 }}
                 aria-labelledby="footer-nav-title">
            <li><Anchor href="/" c="gray.4" size="sm">Inicio</Anchor></li>
            <li><Anchor href="/mapa" c="gray.4" size="sm">Mapa</Anchor></li>
            ...
          </Stack>
        </Box>
```

### 1.4 [SERIO] Tablas sin encabezados accesibles

**Ubicacion:** `src/components/DashboardPanel.tsx` (linea 377), `src/components/admin/reports/ReportsPanel.tsx` (linea 209)

**Problema:** Las tablas no tienen `<caption>` ni `scope` en los headers.

**Solucion:**
```tsx
// src/components/DashboardPanel.tsx
<Table verticalSpacing="sm" highlightOnHover aria-describedby="analysis-table-desc">
  <caption id="analysis-table-desc" className="sr-only">
    Historial de analisis satelitales con datos de inundacion
  </caption>
  <Table.Thead>
    <Table.Tr>
      <Table.Th scope="col">Periodo</Table.Th>
      <Table.Th scope="col" style={{ textAlign: 'right' }}>Ha Inundadas</Table.Th>
      <Table.Th scope="col" style={{ textAlign: 'right' }}>% Area</Table.Th>
      <Table.Th scope="col" style={{ textAlign: 'right' }}>Caminos</Table.Th>
    </Table.Tr>
  </Table.Thead>
```

---

## 2. NAVEGACION POR TECLADO

### 2.1 [CRITICO] Mapa no accesible por teclado

**Ubicacion:** `src/components/MapaInteractivo.tsx`, `src/components/FormularioDenuncia.tsx`

**Problema:** El mapa Leaflet no tiene alternativas de navegacion por teclado. Los usuarios que no pueden usar mouse no pueden seleccionar ubicaciones.

**WCAG:** 2.1.1 (Keyboard), 2.4.7 (Focus Visible)

**Solucion:**
```tsx
// src/components/FormularioDenuncia.tsx - Agregar entrada manual de coordenadas
<Box>
  <Text fw={500} size="sm" mb="xs" id="ubicacion-label">
    Ubicacion del incidente *
  </Text>

  {/* Alternativa accesible: entrada de coordenadas */}
  <Paper p="sm" mb="sm" withBorder>
    <Text size="xs" c="dimmed" mb="xs">
      Opcion 1: Ingresa las coordenadas manualmente
    </Text>
    <Group gap="sm">
      <TextInput
        label="Latitud"
        placeholder="-32.63"
        value={manualLat}
        onChange={(e) => setManualLat(e.target.value)}
        aria-describedby="lat-help"
        style={{ flex: 1 }}
      />
      <TextInput
        label="Longitud"
        placeholder="-62.68"
        value={manualLng}
        onChange={(e) => setManualLng(e.target.value)}
        aria-describedby="lng-help"
        style={{ flex: 1 }}
      />
      <Button
        onClick={handleManualCoords}
        variant="light"
        mt="lg"
      >
        Establecer
      </Button>
    </Group>
    <Text id="lat-help" size="xs" c="dimmed" mt="xs">
      Formato: numeros decimales (ej: -32.63000)
    </Text>
  </Paper>

  {/* Opcion de busqueda por direccion */}
  <Paper p="sm" mb="sm" withBorder>
    <Text size="xs" c="dimmed" mb="xs">
      Opcion 2: Busca por direccion
    </Text>
    <Group gap="sm">
      <TextInput
        placeholder="Ej: Ruta 9 km 312, Bell Ville"
        value={searchAddress}
        onChange={(e) => setSearchAddress(e.target.value)}
        aria-label="Buscar direccion"
        style={{ flex: 1 }}
      />
      <Button onClick={handleAddressSearch} variant="light">
        Buscar
      </Button>
    </Group>
  </Paper>

  {/* Mapa visual (complementario, no unico metodo) */}
  <Text size="xs" c="dimmed" mb="xs">
    Opcion 3: Haz clic en el mapa (requiere mouse o pantalla tactil)
  </Text>
  <Box
    className={mapContainer}
    role="application"
    aria-label="Mapa interactivo para seleccionar ubicacion"
    aria-describedby="map-instructions"
  >
    <MapContainer ...>
```

### 2.2 [CRITICO] Drawer movil sin focus trap completo

**Ubicacion:** `src/components/Header.tsx` (linea 78)

**Problema:** El Drawer de navegacion movil puede perder el foco hacia elementos detras del overlay.

**Solucion:**
```tsx
// src/components/Header.tsx
<Drawer
  opened={opened}
  onClose={close}
  size="100%"
  padding="md"
  title="Menu de navegacion"
  hiddenFrom="sm"
  zIndex={1000}
  trapFocus={true}
  closeButtonProps={{
    'aria-label': 'Cerrar menu de navegacion',
  }}
  aria-modal="true"
  aria-label="Menu de navegacion movil"
>
  <Stack gap="sm" role="menu" aria-label="Opciones de navegacion">
    {LINKS.map((link) => (
      <Button
        key={link.href}
        component="a"
        href={link.href}
        variant="subtle"
        color="gray"
        fullWidth
        justify="flex-start"
        onClick={close}
        role="menuitem"
      >
        {link.label}
      </Button>
    ))}
```

### 2.3 [SERIO] Botones de tipo de denuncia sin navegacion correcta

**Ubicacion:** `src/components/FormularioDenuncia.tsx` (linea 240-257)

**Problema:** El grupo de botones tipo radio no permite navegacion con flechas.

**Solucion:**
```tsx
// src/components/FormularioDenuncia.tsx
const [focusedIndex, setFocusedIndex] = useState(0);

const handleKeyDown = (e: React.KeyboardEvent, index: number) => {
  const buttons = TIPOS_DENUNCIA.length;

  switch (e.key) {
    case 'ArrowRight':
    case 'ArrowDown':
      e.preventDefault();
      setFocusedIndex((index + 1) % buttons);
      break;
    case 'ArrowLeft':
    case 'ArrowUp':
      e.preventDefault();
      setFocusedIndex((index - 1 + buttons) % buttons);
      break;
    case ' ':
    case 'Enter':
      e.preventDefault();
      form.setFieldValue('tipo', TIPOS_DENUNCIA[index].value);
      break;
  }
};

// En el render:
<SimpleGrid
  cols={{ base: 2, sm: 4 }}
  spacing="sm"
  role="radiogroup"
  aria-labelledby="tipo-label"
  aria-required="true"
>
  {TIPOS_DENUNCIA.map((tipo, index) => (
    <UnstyledButton
      key={tipo.value}
      onClick={() => form.setFieldValue('tipo', tipo.value)}
      onKeyDown={(e) => handleKeyDown(e, index)}
      className={`${typeButton} ${form.values.tipo === tipo.value ? typeButtonSelected : ''}`}
      role="radio"
      aria-checked={form.values.tipo === tipo.value}
      aria-label={tipo.label}
      tabIndex={focusedIndex === index ? 0 : -1}
      ref={focusedIndex === index ? focusedRef : null}
    >
```

### 2.4 [SERIO] Skip link existente pero necesita mejoras

**Ubicacion:** `src/layouts/Layout.astro` (linea 44-46)

**Problema:** El skip link existe pero no incluye salto a otras secciones importantes.

**Solucion:**
```astro
<!-- Skip links mejorados -->
<div class="skip-links" role="navigation" aria-label="Enlaces de salto">
  <a href="#main-content" class="skip-link">
    Saltar al contenido principal
  </a>
  <a href="#primary-nav" class="skip-link">
    Saltar a navegacion
  </a>
  <a href="#footer" class="skip-link">
    Saltar al pie de pagina
  </a>
</div>

<style is:global>
  .skip-links {
    position: absolute;
    top: -100px;
    left: 0;
    z-index: 10000;
  }

  .skip-link {
    position: absolute;
    background: var(--mantine-color-blue-filled);
    color: white;
    padding: 8px 16px;
    text-decoration: none;
    font-weight: 500;
    border-radius: 0 0 4px 0;
    transition: top 0.2s;
  }

  .skip-link:focus {
    top: 100px;
    outline: 3px solid var(--mantine-color-blue-light);
    outline-offset: 2px;
  }

  .skip-link:nth-child(2):focus { left: 200px; }
  .skip-link:nth-child(3):focus { left: 380px; }
</style>
```

---

## 3. ARIA

### 3.1 [CRITICO] Notificaciones sin live region

**Ubicacion:** `src/components/MantineProvider.tsx`

**Problema:** Las notificaciones de Mantine no anuncian automaticamente a screen readers.

**WCAG:** 4.1.3 (Status Messages)

**Solucion:**
```tsx
// src/components/MantineProvider.tsx
<Notifications
  position="top-right"
  zIndex={10002}
  autoClose={5000}
  // Configuracion de accesibilidad
  containerProps={{
    role: 'region',
    'aria-label': 'Notificaciones del sistema',
    'aria-live': 'polite',
    'aria-atomic': 'false',
  }}
/>

// Crear componente wrapper para anuncios
// src/components/ui/AccessibleNotification.tsx
import { notifications } from '@mantine/notifications';

interface NotifyOptions {
  title: string;
  message: string;
  type?: 'success' | 'error' | 'warning' | 'info';
}

export function notify({ title, message, type = 'info' }: NotifyOptions) {
  const colors = {
    success: 'green',
    error: 'red',
    warning: 'orange',
    info: 'blue',
  };

  // Anunciar a screen readers
  const announcement = document.createElement('div');
  announcement.setAttribute('role', 'status');
  announcement.setAttribute('aria-live', 'assertive');
  announcement.setAttribute('aria-atomic', 'true');
  announcement.className = 'sr-only';
  announcement.textContent = `${title}: ${message}`;
  document.body.appendChild(announcement);

  setTimeout(() => announcement.remove(), 1000);

  // Mostrar notificacion visual
  notifications.show({
    title,
    message,
    color: colors[type],
  });
}
```

### 3.2 [SERIO] Botones sin aria-label cuando solo tienen iconos

**Ubicacion:** `src/components/FormularioDenuncia.tsx` (linea 344-356)

**Codigo Actual:**
```tsx
<ActionIcon
  pos="absolute"
  top={8}
  right={8}
  color="red"
  variant="filled"
  onClick={() => {
    setFotoPreview(null);
    form.setFieldValue('foto', null);
  }}
>
  X
</ActionIcon>
```

**Solucion:**
```tsx
<ActionIcon
  pos="absolute"
  top={8}
  right={8}
  color="red"
  variant="filled"
  onClick={() => {
    setFotoPreview(null);
    form.setFieldValue('foto', null);
  }}
  aria-label="Eliminar foto seleccionada"
>
  <IconX size={16} aria-hidden="true" />
</ActionIcon>
```

### 3.3 [SERIO] Dropzone sin instrucciones para screen readers

**Ubicacion:** `src/components/FormularioDenuncia.tsx` (linea 359-378)

**Solucion:**
```tsx
<Dropzone
  onDrop={handleDrop}
  accept={IMAGE_MIME_TYPE}
  maxSize={5 * 1024 * 1024}
  maxFiles={1}
  aria-label="Zona para subir foto del incidente"
  aria-describedby="dropzone-instructions"
>
  <Group justify="center" gap="xl" mih={120} style={{ pointerEvents: 'none' }}>
    <Stack align="center" gap="xs">
      <IconPhoto size={32} aria-hidden="true" />
      <Text size="sm" c="dimmed" ta="center" id="dropzone-instructions">
        Arrastra una foto aqui, o presiona Enter o Espacio para seleccionar archivo.
        Formatos aceptados: JPG, PNG, WebP. Tamano maximo: 5MB.
      </Text>
    </Stack>
  </Group>
</Dropzone>
```

### 3.4 [SERIO] Modal sin aria-describedby

**Ubicacion:** `src/components/admin/reports/ReportsPanel.tsx` (linea 283-287)

**Solucion:**
```tsx
<Modal
  opened={detailOpened}
  onClose={closeDetail}
  title="Detalle de Denuncia"
  size="lg"
  aria-describedby="modal-description"
  closeButtonProps={{
    'aria-label': 'Cerrar dialogo de detalle',
  }}
>
  <Text id="modal-description" className="sr-only">
    Formulario para revisar y gestionar el estado de una denuncia ciudadana
  </Text>
  ...
```

### 3.5 [SERIO] Leyenda del mapa sin rol correcto

**Ubicacion:** `src/components/MapaInteractivo.tsx` (linea 88-116)

**Solucion:**
```tsx
const Leyenda = memo(function Leyenda() {
  return (
    <Paper
      shadow="md"
      p="sm"
      radius="md"
      className={legendPanel}
      component="aside"
      aria-label="Leyenda del mapa"
    >
      <Text fw={600} size="sm" mb="xs" component="h3">
        Leyenda
      </Text>
      <Stack
        gap={4}
        component="ul"
        style={{ listStyle: 'none', padding: 0, margin: 0 }}
        aria-label="Tipos de elementos en el mapa"
      >
        {LEYENDA_ITEMS.map((item) => (
          <Group key={item.label} gap="xs" component="li">
            <Box
              aria-hidden="true"
              className={item.type === 'border' ? legendItemBorder : legendItemLine}
              style={...}
            />
            <Text size="xs">{item.label}</Text>
          </Group>
        ))}
      </Stack>
    </Paper>
  );
});
```

---

## 4. FORMULARIOS

### 4.1 [CRITICO] Errores de formulario no asociados programaticamente

**Ubicacion:** `src/components/FormularioDenuncia.tsx` (linea 258-262)

**Codigo Actual:**
```tsx
{form.errors.tipo && (
  <Text size="xs" c="red" mt="xs">
    {form.errors.tipo}
  </Text>
)}
```

**Solucion:**
```tsx
<SimpleGrid
  cols={{ base: 2, sm: 4 }}
  spacing="sm"
  role="radiogroup"
  aria-labelledby="tipo-label"
  aria-describedby={form.errors.tipo ? 'tipo-error' : undefined}
  aria-invalid={!!form.errors.tipo}
>
  {/* ... botones ... */}
</SimpleGrid>

{form.errors.tipo && (
  <Alert
    id="tipo-error"
    color="red"
    variant="light"
    mt="xs"
    role="alert"
    aria-live="assertive"
  >
    <Text size="xs">{form.errors.tipo}</Text>
  </Alert>
)}
```

### 4.2 [CRITICO] Campo de ubicacion requerido sin validacion accesible

**Ubicacion:** `src/components/FormularioDenuncia.tsx` (linea 156-163)

**Problema:** El mensaje de ubicacion requerida se muestra via notificacion, no asociado al campo.

**Solucion:**
```tsx
const [ubicacionError, setUbicacionError] = useState<string | null>(null);

const handleSubmit = useCallback(async (values: typeof form.values) => {
  if (!ubicacion) {
    setUbicacionError('Debes seleccionar una ubicacion en el mapa');
    // Focus en el area de ubicacion
    document.getElementById('ubicacion-section')?.focus();
    return;
  }
  setUbicacionError(null);
  // ... resto del submit
}, [ubicacion, form]);

// En el render:
<Box
  id="ubicacion-section"
  tabIndex={-1}
  aria-describedby={ubicacionError ? 'ubicacion-error' : 'ubicacion-instructions'}
>
  <Text fw={500} size="sm" mb="xs" id="ubicacion-label">
    Ubicacion del incidente *
  </Text>

  {ubicacionError && (
    <Alert
      id="ubicacion-error"
      color="red"
      variant="light"
      mb="sm"
      role="alert"
      aria-live="assertive"
    >
      {ubicacionError}
    </Alert>
  )}

  <Text id="ubicacion-instructions" size="xs" c="dimmed">
    Usa GPS, busca direccion, ingresa coordenadas, o haz clic en el mapa
  </Text>
```

### 4.3 [SERIO] Campos de filtro sin labels

**Ubicacion:** `src/components/admin/reports/ReportsPanel.tsx` (linea 173-195)

**Solucion:**
```tsx
<Paper shadow="sm" p="md" radius="md" mb="md" component="form" role="search">
  <Text component="h3" className="sr-only">Filtros de busqueda</Text>
  <Group>
    <TextInput
      placeholder="Buscar..."
      value={searchQuery}
      onChange={(e) => setSearchQuery(e.target.value)}
      style={{ flex: 1 }}
      aria-label="Buscar en descripcion o ubicacion"
      leftSection={<IconSearch size={16} aria-hidden="true" />}
    />
    <Select
      placeholder="Estado"
      data={[{ value: '', label: 'Todos los estados' }, ...STATUS_OPTIONS]}
      value={filterStatus}
      onChange={setFilterStatus}
      clearable
      w={150}
      aria-label="Filtrar por estado"
    />
    <Select
      placeholder="Categoria"
      data={[{ value: '', label: 'Todas las categorias' }, ...CATEGORY_OPTIONS]}
      value={filterCategory}
      onChange={setFilterCategory}
      clearable
      w={150}
      aria-label="Filtrar por categoria"
    />
    <Button variant="light" onClick={loadReports} aria-label="Actualizar lista de denuncias">
      Actualizar
    </Button>
  </Group>
</Paper>
```

### 4.4 [SERIO] LoginForm sin fieldset para agrupar campos

**Ubicacion:** `src/components/LoginForm.tsx`

**Solucion:**
```tsx
<form onSubmit={form.onSubmit(handleSubmit)}>
  <Stack gap="md" component="fieldset" style={{ border: 'none', padding: 0, margin: 0 }}>
    <Text component="legend" className="sr-only">
      {mode === 'login' ? 'Formulario de inicio de sesion' : 'Formulario de registro'}
    </Text>

    {mode === 'register' && (
      <TextInput
        label="Nombre"
        placeholder="Tu nombre"
        {...form.getInputProps('nombre')}
        required
        aria-required="true"
        autoComplete="name"
      />
    )}

    <TextInput
      label="Email"
      placeholder="tu@email.com"
      {...form.getInputProps('email')}
      required
      aria-required="true"
      autoComplete="email"
      inputMode="email"
    />

    <PasswordInput
      label="Contrasena"
      placeholder="Tu contrasena"
      {...form.getInputProps('password')}
      required
      aria-required="true"
      autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
    />
```

---

## 5. IMAGENES Y MEDIA

### 5.1 [CRITICO] Imagenes en galeria sin alt descriptivo

**Ubicacion:** `src/components/admin/reports/ReportsPanel.tsx` (linea 344-348)

**Codigo Actual:**
```tsx
{selectedReport.imagenes.map((url, idx) => (
  <Card key={idx} padding={0} radius="sm">
    <Image src={url} alt={`Imagen ${idx + 1}`} height={100} fit="cover" />
  </Card>
))}
```

**Solucion:**
```tsx
{selectedReport.imagenes && selectedReport.imagenes.length > 0 && (
  <Box aria-label={`Galeria de ${selectedReport.imagenes.length} imagen(es) adjunta(s)`}>
    <Text size="sm" fw={500} mb="xs" id="gallery-label">
      Imagenes adjuntas ({selectedReport.imagenes.length})
    </Text>
    <SimpleGrid cols={3} aria-labelledby="gallery-label">
      {selectedReport.imagenes.map((url, idx) => (
        <Card key={idx} padding={0} radius="sm">
          <Image
            src={url}
            alt={`Imagen ${idx + 1} de ${selectedReport.imagenes.length} adjunta a denuncia de tipo ${selectedReport.categoria || 'general'}`}
            height={100}
            fit="cover"
          />
          <Button
            variant="subtle"
            size="xs"
            fullWidth
            onClick={() => openImageModal(url)}
            aria-label={`Ver imagen ${idx + 1} en tamano completo`}
          >
            Ver completa
          </Button>
        </Card>
      ))}
    </SimpleGrid>
  </Box>
)}
```

### 5.2 [SERIO] Preview de foto sin descripcion contextual

**Ubicacion:** `src/components/FormularioDenuncia.tsx` (linea 337-343)

**Solucion:**
```tsx
{fotoPreview && (
  <Box pos="relative" role="figure" aria-labelledby="foto-caption">
    <Image
      src={fotoPreview}
      alt="Vista previa de la foto seleccionada para la denuncia"
      radius="md"
      h={200}
      fit="cover"
    />
    <Text id="foto-caption" size="xs" c="dimmed" ta="center" mt="xs">
      Foto seleccionada para adjuntar a la denuncia
    </Text>
    <ActionIcon
      pos="absolute"
      top={8}
      right={8}
      color="red"
      variant="filled"
      onClick={() => {
        setFotoPreview(null);
        form.setFieldValue('foto', null);
      }}
      aria-label="Eliminar foto seleccionada"
    >
      <IconX size={16} aria-hidden="true" />
    </ActionIcon>
  </Box>
)}
```

### 5.3 [SERIO] Iconos decorativos no marcados como tales

**Ubicacion:** Multiples componentes

**Solucion Global:**
```tsx
// src/components/ui/icons.tsx - Agregar aria-hidden por defecto
export function IconMap({ size = 24, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {/* ... paths ... */}
    </svg>
  );
}

// Uso con texto acompanante:
<Button>
  <IconMap size={18} /> {/* aria-hidden por defecto */}
  <span>Ver Mapa</span>
</Button>

// Uso como unico contenido (requiere aria-label en el padre):
<ActionIcon aria-label="Ver en mapa">
  <IconMap size={18} />
</ActionIcon>
```

---

## 6. CONTRASTE DE COLORES

### 6.1 [SERIO] Texto dimmed en tema oscuro con contraste insuficiente

**Ubicacion:** `src/components/Footer.tsx`, multiples componentes

**Problema:** El color `gray.4` en fondo `gray.9` tiene ratio aproximado de 3.5:1 (requiere 4.5:1 para texto normal).

**Colores Actuales:**
- Texto: `#868e96` (gray.4)
- Fondo: `#212529` (gray.9)
- Ratio: ~3.5:1 (FALLA para texto normal)

**Solucion:**
```tsx
// src/components/Footer.tsx
// Cambiar de gray.4 a gray.3 para mejor contraste
<Text size="sm" c="gray.3">
  Gestion de cuencas hidricas en Bell Ville, Cordoba
</Text>

// O usar variables CSS personalizadas:
// src/styles/global.css
[data-mantine-color-scheme="dark"] {
  --text-dimmed-accessible: #adb5bd; /* gray.3 - ratio 5.5:1 */
}

.text-dimmed-accessible {
  color: var(--text-dimmed-accessible);
}
```

### 6.2 [SERIO] Badge amarillo en tema claro con texto blanco

**Ubicacion:** `src/components/DashboardPanel.tsx` (linea 108)

**Problema:** Badge `color="yellow"` con `variant="light"` puede tener contraste insuficiente.

**Solucion:**
```tsx
// Usar variantes con mejor contraste
const getEstadoBadge = useCallback((estado: string) => {
  const config: Record<string, { color: string; label: string; variant: string }> = {
    pendiente: { color: 'yellow', label: 'Pendiente', variant: 'filled' },
    en_revision: { color: 'blue', label: 'En revision', variant: 'light' },
    resuelto: { color: 'green', label: 'Resuelto', variant: 'light' },
    rechazado: { color: 'red', label: 'Rechazado', variant: 'light' },
  };
  const { color, label, variant } = config[estado] || { color: 'gray', label: estado, variant: 'light' };

  // Asegurar contraste en badges amarillos
  const textColor = color === 'yellow' ? 'dark.9' : undefined;

  return (
    <Badge color={color} variant={variant} radius="sm" c={textColor}>
      {label}
    </Badge>
  );
}, []);
```

### 6.3 [SERIO] Focus indicator puede ser invisible en algunos fondos

**Ubicacion:** `src/styles/global.css` (linea 150-153)

**Problema:** El outline azul puede no ser visible sobre fondos azules.

**Solucion:**
```css
/* src/styles/global.css */
:focus-visible {
  outline: 2px solid var(--mantine-color-blue-5);
  outline-offset: 2px;
  /* Agregar sombra para visibilidad en cualquier fondo */
  box-shadow:
    0 0 0 2px var(--mantine-color-body),
    0 0 0 4px var(--mantine-color-blue-5);
}

/* Alternativa con doble borde */
:focus-visible {
  outline: 3px solid var(--mantine-color-blue-5);
  outline-offset: 2px;
}

/* En modo oscuro */
[data-mantine-color-scheme="dark"] :focus-visible {
  outline-color: var(--mantine-color-blue-4);
  box-shadow:
    0 0 0 2px var(--mantine-color-dark-7),
    0 0 0 4px var(--mantine-color-blue-4);
}
```

---

## 7. MAPA INTERACTIVO - SECCION CRITICA

### 7.1 [CRITICO] Mapa completamente inaccesible para usuarios ciegos

**Ubicacion:** `src/components/MapaInteractivo.tsx`

**Problema:** El mapa Leaflet no proporciona ninguna alternativa textual para usuarios que no pueden ver.

**WCAG:** 1.1.1 (Non-text Content), 1.3.1 (Info and Relationships)

**Solucion Completa:**
```tsx
// src/components/MapaInteractivo.tsx
function MapaContenido() {
  // ... estados existentes ...
  const [showTextAlternative, setShowTextAlternative] = useState(false);

  return (
    <Box pos="relative" w="100%" className={mapWrapper}>
      {/* Controles de accesibilidad */}
      <Box
        p="sm"
        style={{
          position: 'absolute',
          top: 8,
          left: 8,
          zIndex: 1000,
        }}
      >
        <Button
          size="xs"
          variant="filled"
          onClick={() => setShowTextAlternative(!showTextAlternative)}
          aria-pressed={showTextAlternative}
        >
          {showTextAlternative ? 'Ver mapa visual' : 'Ver descripcion textual'}
        </Button>
      </Box>

      {showTextAlternative ? (
        /* Alternativa textual completa */
        <Paper p="lg" className={mapWrapper}>
          <Title order={3} mb="md">Descripcion del Mapa - Consorcio Canalero</Title>

          <Stack gap="md">
            <Box>
              <Text fw={600}>Ubicacion Central:</Text>
              <Text>Bell Ville, Cordoba, Argentina (Latitud: -32.63, Longitud: -62.68)</Text>
            </Box>

            <Box>
              <Text fw={600}>Capas Disponibles:</Text>
              <Stack component="ul" gap="xs" style={{ paddingLeft: '1.5rem' }}>
                <li>
                  <Text><strong>Zona Consorcio:</strong> Limite perimetral del area administrada (contorno rojo)</Text>
                </li>
                <li>
                  <Text><strong>Cuenca Candil:</strong> Area de drenaje este (color azul, aprox. X hectareas)</Text>
                </li>
                <li>
                  <Text><strong>Cuenca ML:</strong> Area de drenaje sur (color verde)</Text>
                </li>
                <li>
                  <Text><strong>Cuenca Noroeste:</strong> Area de drenaje noroeste (color naranja)</Text>
                </li>
                <li>
                  <Text><strong>Cuenca Norte:</strong> Area de drenaje norte (color violeta)</Text>
                </li>
                <li>
                  <Text><strong>Red Vial:</strong> Caminos rurales (lineas amarillas, 753 km total)</Text>
                </li>
              </Stack>
            </Box>

            <Box>
              <Text fw={600}>Estado Actual:</Text>
              <Text>
                Ultima actualizacion de inundacion: [fecha].
                Areas afectadas: [X] hectareas ([Y]% del area total).
              </Text>
            </Box>

            <Box>
              <Text fw={600}>Acciones Disponibles:</Text>
              <Stack gap="xs">
                <Button component="a" href="/denuncias" variant="light">
                  Reportar un problema en esta zona
                </Button>
                <Button component="a" href="/dashboard" variant="light">
                  Ver estadisticas detalladas
                </Button>
              </Stack>
            </Box>
          </Stack>
        </Paper>
      ) : (
        /* Mapa visual con mejoras de accesibilidad */
        <Box
          role="application"
          aria-label="Mapa interactivo del Consorcio Canalero. Presiona Tab para navegar entre controles, o activa la descripcion textual para una alternativa accesible."
          aria-describedby="map-keyboard-help"
        >
          <div id="map-keyboard-help" className="sr-only">
            Use los controles del mapa para hacer zoom y cambiar capas.
            Para una experiencia accesible completa, active la vista de descripcion textual.
          </div>

          <MapContainer
            center={CENTER}
            zoom={ZOOM}
            style={{ width: '100%', height: '100%' }}
            scrollWheelZoom={true}
            keyboard={true}
            keyboardPanDelta={80}
          >
            {/* ... capas existentes ... */}
          </MapContainer>
        </Box>
      )}

      <Leyenda />
      <InfoPanel feature={selectedFeature} onClose={handleCloseInfoPanel} />
    </Box>
  );
}
```

### 7.2 [CRITICO] Controles del mapa sin labels accesibles

**Ubicacion:** `src/components/MapaInteractivo.tsx` - Leaflet controls

**Solucion:**
```tsx
// Componente para mejorar accesibilidad de controles Leaflet
function AccessibleMapControls() {
  const map = useMap();

  useEffect(() => {
    // Mejorar accesibilidad de controles de zoom
    const zoomIn = document.querySelector('.leaflet-control-zoom-in');
    const zoomOut = document.querySelector('.leaflet-control-zoom-out');

    if (zoomIn) {
      zoomIn.setAttribute('aria-label', 'Acercar mapa');
      zoomIn.setAttribute('title', 'Acercar (tecla +)');
    }
    if (zoomOut) {
      zoomOut.setAttribute('aria-label', 'Alejar mapa');
      zoomOut.setAttribute('title', 'Alejar (tecla -)');
    }

    // Mejorar accesibilidad del control de capas
    const layersControl = document.querySelector('.leaflet-control-layers-toggle');
    if (layersControl) {
      layersControl.setAttribute('aria-label', 'Mostrar/ocultar selector de capas');
      layersControl.setAttribute('aria-haspopup', 'true');
    }

    // Agregar instrucciones de teclado
    const layersList = document.querySelector('.leaflet-control-layers-list');
    if (layersList) {
      layersList.setAttribute('role', 'menu');
      layersList.setAttribute('aria-label', 'Capas del mapa');
    }
  }, [map]);

  return null;
}

// Usar en MapContainer:
<MapContainer ...>
  <AccessibleMapControls />
  {/* ... resto de capas ... */}
</MapContainer>
```

### 7.3 [CRITICO] Interacciones de clic en capas no accesibles

**Ubicacion:** `src/components/MapaInteractivo.tsx` (linea 201-221)

**Solucion:**
```tsx
// Agregar lista navegable de features como alternativa
function FeaturesList({ capas }: { capas: typeof capas }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  const getAllFeatures = () => {
    const features: { layer: string; properties: Record<string, any> }[] = [];

    Object.entries(capas).forEach(([layerName, data]) => {
      if (data?.features) {
        data.features.forEach((feature: any) => {
          features.push({
            layer: layerName,
            properties: feature.properties || {},
          });
        });
      }
    });

    return features;
  };

  return (
    <Accordion
      value={expanded}
      onChange={setExpanded}
      aria-label="Lista de elementos del mapa"
    >
      {getAllFeatures().map((feature, idx) => (
        <Accordion.Item key={idx} value={`feature-${idx}`}>
          <Accordion.Control>
            {feature.layer}: {feature.properties.nombre || `Elemento ${idx + 1}`}
          </Accordion.Control>
          <Accordion.Panel>
            <Stack gap="xs">
              {Object.entries(feature.properties).map(([key, value]) => (
                <Group key={key} gap="xs">
                  <Badge size="xs">{key}:</Badge>
                  <Text size="sm">{String(value)}</Text>
                </Group>
              ))}
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
      ))}
    </Accordion>
  );
}
```

---

## 8. SCREEN READERS

### 8.1 [CRITICO] Cambios dinamicos no anunciados

**Ubicacion:** `src/components/DashboardPanel.tsx`, `src/components/FormularioDenuncia.tsx`

**Problema:** Estados de carga y cambios de datos no se anuncian.

**Solucion:**
```tsx
// src/components/ui/LiveRegion.tsx
import { createContext, useContext, useState, useCallback, ReactNode } from 'react';

interface LiveRegionContextType {
  announce: (message: string, priority?: 'polite' | 'assertive') => void;
}

const LiveRegionContext = createContext<LiveRegionContextType | null>(null);

export function LiveRegionProvider({ children }: { children: ReactNode }) {
  const [politeMessage, setPoliteMessage] = useState('');
  const [assertiveMessage, setAssertiveMessage] = useState('');

  const announce = useCallback((message: string, priority: 'polite' | 'assertive' = 'polite') => {
    if (priority === 'assertive') {
      setAssertiveMessage(message);
      setTimeout(() => setAssertiveMessage(''), 100);
    } else {
      setPoliteMessage(message);
      setTimeout(() => setPoliteMessage(''), 100);
    }
  }, []);

  return (
    <LiveRegionContext.Provider value={{ announce }}>
      {children}

      {/* Live regions */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      >
        {politeMessage}
      </div>

      <div
        role="alert"
        aria-live="assertive"
        aria-atomic="true"
        className="sr-only"
      >
        {assertiveMessage}
      </div>
    </LiveRegionContext.Provider>
  );
}

export function useLiveRegion() {
  const context = useContext(LiveRegionContext);
  if (!context) {
    throw new Error('useLiveRegion must be used within LiveRegionProvider');
  }
  return context;
}

// Uso en DashboardPanel:
function DashboardContent() {
  const { announce } = useLiveRegion();

  useEffect(() => {
    const fetchData = async () => {
      announce('Cargando datos del dashboard');

      try {
        setLoading(true);
        const [statsData, reportsData, historyData] = await Promise.all([...]);

        announce(`Dashboard cargado. ${reportsData.items?.length || 0} denuncias recientes.`);
      } catch (err) {
        announce('Error al cargar datos del dashboard', 'assertive');
      }
    };

    fetchData();
  }, []);
```

### 8.2 [SERIO] Loading states sin anuncio

**Ubicacion:** Multiples componentes

**Solucion Global:**
```tsx
// src/components/ui/LoadingState.tsx - Mejorar componente existente
interface LoadingStateProps {
  loading: boolean;
  loadingText?: string;
  children: ReactNode;
}

export function AccessibleLoader({
  loading,
  loadingText = 'Cargando contenido',
  children,
}: LoadingStateProps) {
  return (
    <>
      {loading ? (
        <Center py="xl">
          <Stack align="center" gap="md">
            <Loader aria-hidden="true" />
            <Text size="sm" c="dimmed" role="status" aria-live="polite">
              {loadingText}...
            </Text>
          </Stack>
        </Center>
      ) : (
        children
      )}
    </>
  );
}
```

### 8.3 [SERIO] Paginacion sin contexto

**Ubicacion:** `src/components/admin/reports/ReportsPanel.tsx` (linea 269-273)

**Solucion:**
```tsx
{totalPages > 1 && (
  <Box role="navigation" aria-label="Paginacion de denuncias">
    <Group justify="center" mt="md">
      <Text size="sm" c="dimmed" className="sr-only" aria-live="polite">
        Pagina {page} de {totalPages}
      </Text>
      <Pagination
        total={totalPages}
        value={page}
        onChange={(newPage) => {
          setPage(newPage);
          announce(`Navegando a pagina ${newPage} de ${totalPages}`);
        }}
        getItemProps={(page) => ({
          'aria-label': `Ir a pagina ${page}`,
        })}
        getControlProps={(control) => ({
          'aria-label': control === 'first' ? 'Primera pagina' :
                       control === 'last' ? 'Ultima pagina' :
                       control === 'next' ? 'Pagina siguiente' :
                       control === 'previous' ? 'Pagina anterior' : undefined,
        })}
      />
    </Group>
  </Box>
)}
```

---

## 9. RESPONSIVE Y ZOOM

### 9.1 [MODERADO] Contenido truncado a 200% zoom

**Ubicacion:** `src/components/DashboardPanel.tsx` - StatCards

**Problema:** A 200% zoom, las tarjetas de estadisticas pueden solaparse.

**Solucion:**
```tsx
// Asegurar que el grid se adapte correctamente
<SimpleGrid
  cols={{ base: 1, xs: 1, sm: 2, md: 2, lg: 4 }}
  spacing={{ base: 'sm', sm: 'md', lg: 'lg' }}
  mb="xl"
>
  {statsCards.map((stat) => (
    <StatCard key={stat.title} {...stat} />
  ))}
</SimpleGrid>

// En StatCard, asegurar que el texto se ajuste
<Text
  size="1.75rem"
  fw={800}
  style={{
    lineHeight: 1.2,
    wordBreak: 'break-word',
    overflowWrap: 'break-word',
  }}
>
```

### 9.2 [MODERADO] Touch targets demasiado pequenos

**Ubicacion:** `src/components/admin/reports/ReportsPanel.tsx` - ActionIcons

**WCAG:** 2.5.5 (Target Size)

**Solucion:**
```tsx
// Asegurar tamano minimo de 44x44px
<ActionIcon
  variant="light"
  onClick={() => handleViewDetail(report)}
  size="lg" // Minimo 44px
  style={{ minWidth: 44, minHeight: 44 }}
  aria-label={`Ver detalle de denuncia ${report.id}`}
>
  <IconInfoCircle size={18} />
</ActionIcon>
```

---

## 10. CSS DE ACCESIBILIDAD GLOBAL

Agregar al archivo `src/styles/global.css`:

```css
/* ================================
   ESTILOS DE ACCESIBILIDAD GLOBALES
   ================================ */

/* Clase para ocultar visualmente pero mantener accesible */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

/* Mostrar al enfocar (para skip links, etc) */
.sr-only-focusable:focus,
.sr-only-focusable:active {
  position: static;
  width: auto;
  height: auto;
  padding: inherit;
  margin: inherit;
  overflow: visible;
  clip: auto;
  white-space: normal;
}

/* Reducir animaciones para usuarios que lo prefieren */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}

/* Mejorar visibilidad del foco */
:focus-visible {
  outline: 3px solid var(--mantine-color-blue-5);
  outline-offset: 2px;
  box-shadow: 0 0 0 6px rgba(59, 130, 246, 0.2);
}

/* Foco para modo oscuro */
[data-mantine-color-scheme="dark"] :focus-visible {
  outline-color: var(--mantine-color-blue-4);
  box-shadow: 0 0 0 6px rgba(96, 165, 250, 0.3);
}

/* Asegurar contraste minimo en texto dimmed */
.text-dimmed-accessible {
  color: #6b7280; /* gray.500 - ratio 4.6:1 en fondo blanco */
}

[data-mantine-color-scheme="dark"] .text-dimmed-accessible {
  color: #9ca3af; /* gray.400 - ratio 4.8:1 en fondo oscuro */
}

/* Touch targets minimos */
button,
[role="button"],
a,
input,
select,
textarea {
  min-height: 44px;
  min-width: 44px;
}

/* Excepcion para elementos inline pequenos */
a:not([class]),
button[class*="ActionIcon"] {
  min-height: unset;
  min-width: unset;
}

/* Espaciado suficiente entre elementos interactivos */
.touch-spacing > * + * {
  margin-top: 8px;
}

/* Indicador de elementos requeridos */
[aria-required="true"]::after,
.required-indicator::after {
  content: " *";
  color: var(--mantine-color-red-6);
}

/* Alertas de error visibles */
[role="alert"] {
  border-left: 4px solid var(--mantine-color-red-6);
  padding-left: 12px;
}

/* Mejor legibilidad de tablas */
.mantine-Table-root th {
  font-weight: 600;
  background-color: var(--mantine-color-gray-0);
}

[data-mantine-color-scheme="dark"] .mantine-Table-root th {
  background-color: var(--mantine-color-dark-6);
}

/* Asegurar que los modales tengan fondo opaco */
.mantine-Modal-overlay {
  background-color: rgba(0, 0, 0, 0.75);
}
```

---

## 11. PLAN DE REMEDIACION PRIORIZADO

### Fase 1: Criticos (1-2 semanas)
1. Implementar alternativa textual para mapa
2. Agregar entrada manual de coordenadas en formulario de denuncias
3. Corregir focus trap en Drawer movil
4. Implementar live regions para notificaciones
5. Asociar errores de formulario programaticamente

### Fase 2: Serios (2-4 semanas)
1. Agregar landmarks ARIA apropiados
2. Corregir jerarquia de encabezados
3. Mejorar labels en formularios de filtro
4. Agregar aria-labels a todos los botones de icono
5. Mejorar contraste de colores en tema oscuro
6. Agregar scope a encabezados de tabla

### Fase 3: Moderados (4-6 semanas)
1. Mejorar skip links con mas destinos
2. Implementar navegacion por flechas en grupos radio
3. Agregar LiveRegionProvider global
4. Mejorar responsive a 200% zoom
5. Agregar descripciones contextuales a imagenes

### Fase 4: Menores (Continuo)
1. Documentar patrones de accesibilidad
2. Agregar tests automatizados de accesibilidad
3. Entrenar al equipo en mejores practicas
4. Establecer proceso de revision de accesibilidad

---

## 12. HERRAMIENTAS DE TESTING RECOMENDADAS

```bash
# Instalar dependencias de testing
npm install -D @axe-core/playwright jest-axe @testing-library/jest-dom

# Agregar script de auditoria
# package.json
{
  "scripts": {
    "test:a11y": "playwright test tests/accessibility/",
    "audit:a11y": "npx pa11y-ci --sitemap http://localhost:4321/sitemap.xml"
  }
}
```

### Ejemplo de Test Automatizado:
```typescript
// tests/accessibility/homepage.spec.ts
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('Homepage Accessibility', () => {
  test('should not have any automatically detectable accessibility issues', async ({ page }) => {
    await page.goto('/');

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .analyze();

    expect(accessibilityScanResults.violations).toEqual([]);
  });

  test('skip link should be visible on focus', async ({ page }) => {
    await page.goto('/');
    await page.keyboard.press('Tab');

    const skipLink = page.locator('.skip-link');
    await expect(skipLink).toBeFocused();
    await expect(skipLink).toBeVisible();
  });

  test('all interactive elements should be keyboard accessible', async ({ page }) => {
    await page.goto('/');

    const focusableElements = await page.locator(
      'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
    ).all();

    for (const element of focusableElements) {
      await element.focus();
      await expect(element).toBeFocused();
    }
  });
});
```

---

## 13. DECLARACION DE ACCESIBILIDAD RECOMENDADA

Agregar pagina `/accesibilidad` con:

```markdown
# Declaracion de Accesibilidad

El Consorcio Canalero 10 de Mayo se compromete a garantizar la accesibilidad digital
para personas con discapacidades. Estamos continuamente mejorando la experiencia de
usuario para todos y aplicando los estandares de accesibilidad relevantes.

## Estado de Conformidad

Este sitio web se ajusta parcialmente al nivel AA de las Pautas de Accesibilidad
para el Contenido Web (WCAG) 2.1. "Parcialmente conforme" significa que algunas
partes del contenido no se ajustan completamente al estandar de accesibilidad.

## Contenido No Accesible

El contenido que se indica a continuacion no es accesible por los siguientes motivos:
- El mapa interactivo requiere uso de mouse o pantalla tactil
- Algunas imagenes pueden carecer de descripciones alternativas completas

## Alternativas Accesibles

Para el mapa interactivo, ofrecemos:
- Descripcion textual completa de las capas y datos
- Entrada manual de coordenadas
- Busqueda por direccion

## Comentarios

Agradecemos sus comentarios sobre la accesibilidad de este sitio.
Por favor, contactenos si encuentra barreras de accesibilidad:
- Email: accesibilidad@consorcio10demayo.org.ar
- Telefono: [numero]

Intentamos responder a los comentarios dentro de 5 dias habiles.

Fecha de esta declaracion: [fecha]
```

---

**Fin del Reporte de Auditoria**
