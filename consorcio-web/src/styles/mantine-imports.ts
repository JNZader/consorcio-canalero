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
