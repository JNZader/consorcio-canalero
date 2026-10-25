/**
 * Mensajes de error de la interfaz, en español rioplatense (voseo).
 *
 * El título dice qué no se pudo hacer. El detalle dice qué puede hacer
 * la persona. El título no empieza por un prefijo genérico.
 */

export interface MensajeError {
  readonly titulo: string;
  readonly detalle: string;
}

export function mensajeError(titulo: string, detalle: string): MensajeError {
  return { titulo, detalle };
}

/** Una frase para anuncios, alerts y `Error.message`. */
export function textoError(mensaje: MensajeError, extra?: string): string {
  const detalle = extra ? `${extra} ${mensaje.detalle}` : mensaje.detalle;
  return `${mensaje.titulo}. ${detalle}`;
}

export const erroresUi = {
  iniciarSesion: mensajeError(
    'No pudimos iniciar sesión',
    'Revisá el correo y la contraseña. Si no la recordás, recuperá el acceso.'
  ),
  crearCuenta: mensajeError(
    'No pudimos crear la cuenta',
    'Revisá el nombre, el correo y la contraseña. Si el correo ya está registrado, iniciá sesión.'
  ),
  google: mensajeError(
    'No pudimos conectar con Google',
    'Volvé a intentar. Si sigue igual, entrá con correo y contraseña.'
  ),
  recuperarClave: mensajeError(
    'No pudimos enviar el correo de recuperación',
    'Revisá que el email esté bien escrito y volvé a intentar en unos minutos.'
  ),
  restablecerClave: mensajeError(
    'No pudimos restablecer la contraseña',
    'Pedí un enlace nuevo y volvé a intentar.'
  ),
  cambiarClave: mensajeError(
    'No pudimos cambiar la contraseña',
    'Revisá que cumpla los requisitos y volvé a intentar.'
  ),
  verificarCorreo: mensajeError(
    'No pudimos verificar el correo',
    'Pedí un enlace nuevo y abrilo desde el mismo navegador.'
  ),
  perfilOAuth: mensajeError(
    'No pudimos leer tu perfil',
    'Volvé a iniciar sesión. Si sigue igual, probá en unos minutos.'
  ),
  inicializarSesion: mensajeError('No pudimos restaurar tu sesión', 'Volvé a iniciar sesión.'),
  perfilUsuario: mensajeError('No pudimos leer tu perfil', 'Cerrá sesión y volvé a entrar.'),
  buscarDireccion: mensajeError(
    'No pudimos buscar la dirección',
    'Revisá el texto o ingresá la latitud y la longitud a mano.'
  ),
  cargarDenuncias: mensajeError(
    'No pudimos cargar las denuncias',
    'Actualizá la página. Si sigue igual, esperá un momento y volvé a entrar.'
  ),
  actualizarDenuncia: mensajeError(
    'No pudimos guardar el cambio de la denuncia',
    'Revisá la conexión y volvé a intentar.'
  ),
  enviarDenuncia: mensajeError(
    'No pudimos enviar la denuncia',
    'Revisá la conexión y volvé a intentar. Si ya la cargaste, no la dupliques.'
  ),
  misDenuncias: mensajeError(
    'No pudimos cargar tus denuncias',
    'Actualizá la página. Si sigue igual, volvé a entrar más tarde.'
  ),
  misSugerencias: mensajeError(
    'No pudimos cargar tus sugerencias',
    'Actualizá la página. Si sigue igual, volvé a entrar más tarde.'
  ),
  cargarTramites: mensajeError(
    'No pudimos cargar los trámites',
    'Tocá Reintentar. Si sigue igual, esperá un momento y volvé a entrar.'
  ),
  cargarMapa: mensajeError(
    'No pudimos cargar el mapa',
    'Recargá la página. Si sigue igual, probá de nuevo en unos minutos.'
  ),
  cargarPadron: mensajeError(
    'No pudimos cargar el padrón',
    'Revisá la conexión y actualizá la búsqueda.'
  ),
  crearConsorcista: mensajeError(
    'No pudimos registrar al consorcista',
    'Revisá el CUIT, el nombre y el apellido, y volvé a intentar.'
  ),
  importarPadron: mensajeError(
    'No pudimos importar el padrón',
    'Usá un archivo CSV, XLS o XLSX y volvé a subirlo.'
  ),
  descargarTramite: mensajeError(
    'No pudimos descargar el trámite',
    'Volvé a intentar. Si sigue fallando, recargá la página.'
  ),
  descargarResumen: mensajeError(
    'No pudimos descargar el resumen financiero',
    'Volvé a intentar en unos segundos.'
  ),
  generarPdf: mensajeError(
    'No pudimos generar el PDF',
    'Volvé a intentar. Si el mapa está cargando, esperá a que termine.'
  ),
  pdfInvalido: mensajeError(
    'No pudimos preparar el PDF',
    'El servidor no devolvió un documento. Volvé a intentar.'
  ),
  exportarDashboard: mensajeError(
    'No pudimos exportar los datos del tablero',
    'Volvé a intentar en unos segundos.'
  ),
  importarArchivo: mensajeError(
    'No pudimos importar el archivo',
    'Revisá que sea un GeoJSON válido y volvé a subirlo.'
  ),
  importarSubcuencas: mensajeError(
    'No pudimos importar las subcuencas',
    'Revisá el GeoJSON y volvé a subirlo.'
  ),
  importarZonificacion: mensajeError(
    'No pudimos importar la zonificación',
    'Revisá el GeoJSON y volvé a subirlo.'
  ),
  exportarBundle: mensajeError(
    'No pudimos exportar el paquete geoespacial',
    'Volvé a intentar. Si el archivo es grande, esperá y reintentá.'
  ),
  importarBundle: mensajeError(
    'No pudimos importar el paquete geoespacial',
    'Revisá que el ZIP sea el paquete exportado y volvé a subirlo.'
  ),
  cargarDashboard: mensajeError(
    'No pudimos cargar los datos del tablero',
    'Verificá que el servidor esté activo y tocá Reintentar.'
  ),
  seccion: mensajeError('No pudimos mostrar esta sección', 'Tocá Reintentar o recargá la página.'),
  subirArchivo: mensajeError(
    'No pudimos subir el archivo',
    'Revisá el formato y el tamaño, y volvé a intentar.'
  ),
  subirFoto: mensajeError(
    'No pudimos subir la foto',
    'Probá con otra imagen (JPG o PNG) y volvé a intentar.'
  ),
  exportarDatos: mensajeError(
    'No pudimos exportar los datos',
    'Volvé a intentar en unos segundos.'
  ),
  cargarSuelos: mensajeError(
    'No pudimos cargar la capa de suelos',
    'Revisá la conexión y volvé a abrir el mapa.'
  ),
  iniciarPipeline: mensajeError(
    'No pudimos iniciar el procesamiento del terreno',
    'Volvé a intentar en unos minutos.'
  ),
} as const;
