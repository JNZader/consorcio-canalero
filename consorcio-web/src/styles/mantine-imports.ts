/**
 * Imports centralizados de estilos CSS de Mantine.
 *
 * Este archivo es el UNICO lugar donde se importan los estilos de Mantine.
 * Todos los providers (AppProvider, MantineProvider) deben importar desde aqui.
 *
 * Esto evita la duplicacion de imports CSS y asegura consistencia.
 */

// Estilos core de Mantine (requerido)
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
