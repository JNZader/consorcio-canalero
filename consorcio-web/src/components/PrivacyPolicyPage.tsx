/**
 * Privacy policy page — Ley 25.326 compliance (Phase 4 / F4-J).
 *
 * Texto base genérico que cubre los puntos exigidos por la Ley
 * Nacional de Protección de Datos Personales (25.326) y su
 * reglamentación. PLEASE — un abogado debe revisar este texto antes
 * de publicarlo como definitivo; las URLs / fechas concretas pueden
 * cambiar entre deploys. La página existe para no quedar SIN política
 * pública mientras se afina el contenido legal.
 */

import { Anchor, Container, List, Paper, Stack, Text, Title } from '@mantine/core';

export default function PrivacyPolicyPage() {
  return (
    <Container size="md" py="xl">
      <Paper p="xl" withBorder shadow="sm">
        <Stack gap="md">
          <Title order={1}>Política de Privacidad</Title>
          <Text size="sm" c="dimmed">
            Última actualización: 19 de mayo de 2026 — Versión 1.0
          </Text>

          <Text>
            El <strong>Consorcio Canalero 10 de Mayo</strong> (en adelante,
            "el Consorcio") informa a sus consorcistas, ciudadanos usuarios
            y visitantes sobre el tratamiento de sus datos personales en el
            marco de la{' '}
            <Anchor
              href="https://servicios.infoleg.gob.ar/infolegInternet/anexos/60000-64999/64790/norma.htm"
              target="_blank"
              rel="noopener noreferrer"
            >
              Ley Nacional N.º 25.326
            </Anchor>{' '}
            de Protección de los Datos Personales y normativa concordante.
          </Text>

          <Title order={2} size="h3">
            1. Datos que recolectamos
          </Title>
          <List>
            <List.Item>
              <strong>Padrón de consorcistas</strong>: nombre, apellido,
              CUIT, DNI, domicilio, teléfono, correo electrónico,
              identificación parcelaria, hectáreas, categoría.
            </List.Item>
            <List.Item>
              <strong>Denuncias ciudadanas</strong>: descripción del
              incidente, coordenadas geográficas reportadas, foto opcional
              (sin metadatos GPS — ver § 4), correo electrónico del usuario
              registrado, teléfono de contacto si lo provee.
            </List.Item>
            <List.Item>
              <strong>Cuentas de usuario</strong>: correo electrónico,
              contraseña almacenada como hash criptográfico
              (no recuperable), rol asignado.
            </List.Item>
            <List.Item>
              <strong>Datos de uso</strong>: dirección IP y user-agent
              registrados de forma agregada para detección de abuso. No se
              construyen perfiles de navegación.
            </List.Item>
          </List>
          <Text size="sm">
            No recolectamos datos sensibles en el sentido del Art. 7 de la
            Ley (origen racial, opinión política, convicción religiosa,
            salud, vida sexual).
          </Text>

          <Title order={2} size="h3">
            2. Finalidad del tratamiento
          </Title>
          <List>
            <List.Item>
              Gestión administrativa del padrón de consorcistas (cuotas,
              comunicaciones oficiales, asambleas).
            </List.Item>
            <List.Item>
              Recepción y seguimiento de denuncias y sugerencias
              ciudadanas relacionadas con la infraestructura hídrica del
              consorcio.
            </List.Item>
            <List.Item>
              Análisis territorial y operativo agregado (monitoreo de
              cuencas, planificación de obras).
            </List.Item>
          </List>
          <Text size="sm">
            Los datos NO se comercializan, ceden ni transfieren a
            terceros con fines de marketing. Se comparten exclusivamente
            con autoridades públicas competentes cuando exista
            requerimiento legal escrito.
          </Text>

          <Title order={2} size="h3">
            3. Conservación
          </Title>
          <List>
            <List.Item>
              Padrón: mientras el titular mantenga su condición de
              consorcista; archivado por 10 años posteriores a la baja
              para cumplir obligaciones contables.
            </List.Item>
            <List.Item>
              Denuncias: mientras la denuncia esté abierta + 6 meses tras
              su resolución. La foto se borra del almacenamiento al
              cerrarse la denuncia; el registro textual se conserva con
              fines estadísticos agregados y anonimizados.
            </List.Item>
            <List.Item>
              Cuentas: mientras el usuario las mantenga activas; eliminadas
              a su solicitud (ver § 5).
            </List.Item>
          </List>

          <Title order={2} size="h3">
            4. Seguridad
          </Title>
          <Text>
            El Consorcio implementa medidas técnicas y organizativas
            razonables: cifrado en tránsito (HTTPS/TLS), cifrado en reposo
            de las copias de respaldo, control de acceso por rol, registro
            de auditoría de consultas catastrales, ausencia de metadatos
            de geolocalización en las fotos almacenadas (las coordenadas
            EXIF GPS son eliminadas en el momento de la carga), tokens de
            sesión de corta duración con rotación. Los proveedores que
            procesan datos en nuestro nombre (alojamiento en Hetzner,
            correo transaccional, monitoreo de errores) están listados en
            la sección "Encargados de tratamiento" disponible bajo
            solicitud.
          </Text>

          <Title order={2} size="h3">
            5. Sus derechos (ARCO)
          </Title>
          <Text>
            Como titular de los datos usted tiene derecho a:
          </Text>
          <List>
            <List.Item>
              <strong>Acceder</strong> a los datos personales que tenemos
              sobre usted (10 días corridos para responder).
            </List.Item>
            <List.Item>
              <strong>Rectificarlos</strong> si están desactualizados,
              inexactos o incompletos (5 días corridos).
            </List.Item>
            <List.Item>
              <strong>Solicitar su supresión</strong> (cancelación) cuando
              ya no sean necesarios para la finalidad declarada. Los
              consorcistas registrados en el padrón pueden necesitar
              mantener algunos datos por requisitos legales; en ese caso
              se anonimizan en lugar de borrarse.
            </List.Item>
            <List.Item>
              <strong>Oponerse</strong> al tratamiento para usos no
              esenciales del servicio.
            </List.Item>
          </List>
          <Text>
            Para ejercer cualquiera de estos derechos puede escribir a{' '}
            <Anchor href="mailto:contacto@consorcio10demayo.gob.ar">
              contacto@consorcio10demayo.gob.ar
            </Anchor>{' '}
            adjuntando una copia de su documento de identidad para
            verificar la titularidad. La solicitud y la respuesta son
            gratuitas.
          </Text>
          <Text>
            Si considera que el Consorcio no atendió correctamente su
            solicitud, puede reclamar ante la{' '}
            <Anchor
              href="https://www.argentina.gob.ar/aaip/datospersonales"
              target="_blank"
              rel="noopener noreferrer"
            >
              Agencia de Acceso a la Información Pública (AAIP)
            </Anchor>{' '}
            como órgano de control en los términos de la Ley 25.326.
          </Text>

          <Title order={2} size="h3">
            6. Cookies y almacenamiento local
          </Title>
          <Text>
            Esta aplicación utiliza almacenamiento local del navegador
            (sessionStorage) para mantener su sesión iniciada y cookies
            HttpOnly imprescindibles para el flujo de autenticación
            (oauth_state, refresh_token). No utilizamos cookies de terceros
            con fines publicitarios o de seguimiento.
          </Text>

          <Title order={2} size="h3">
            7. Cambios a esta política
          </Title>
          <Text>
            Cualquier cambio sustancial será anunciado en la página de
            inicio antes de entrar en vigencia. La fecha al inicio de este
            documento refleja la última actualización.
          </Text>

          <Text size="xs" c="dimmed" mt="lg">
            Para el Banco de Datos del Consorcio Canalero 10 de Mayo
            inscripto ante el Registro Nacional de Bases de Datos — AAIP.
          </Text>
        </Stack>
      </Paper>
    </Container>
  );
}
