/**
 * Imports centralizados de estilos CSS de Mantine.
 *
 * Este archivo es el UNICO lugar donde se importan los estilos de Mantine.
 * Todos los providers (AppProvider, MantineProvider) deben importar desde aqui.
 *
 * Esto evita la duplicacion de imports CSS y asegura consistencia.
 */

// Estilos core de Mantine — bundle monolítico.
//
// Phase 3 / F3-D considered swapping this for granular per-component
// imports (``@mantine/core/styles/Button.css`` etc.) to drop the
// uncompressed 228 KB down to whatever subset we actually use. The
// audit listed 43 distinct components across 105 files — each
// migration is mechanically safe but the surface for a forgotten
// import (e.g. a Tooltip that suddenly renders without animation
// because its CSS wasn't included) is large. Skipped: 228 KB raw =
// ~30 KB gzipped + the SW caches it for a year. Re-evaluate when
// Mantine v9 ships its rumoured CSS-tree-shaking story.
import '@mantine/core/styles.css';

// Estilos de notificaciones (usado en AppProvider y MantineProvider)
import '@mantine/notifications/styles.css';

// Estilos de dropzone (usado en formularios de archivos)
import '@mantine/dropzone/styles.css';

// Estilos del paquete de fechas (DatePicker, DatePickerInput,
// DateTimePicker). Sin esto los chevrones del header del calendario se
// renderizan a tamaño SVG natural (gigantes) y la grilla queda
// desalineada — visible a ojo en SuggestionDetailModal cuando se abre
// "Agendar para Reunión".
import '@mantine/dates/styles.css';
