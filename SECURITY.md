# Seguridad

## Versiones con soporte

Solo la última versión publicada recibe correcciones.

## Reportar una vulnerabilidad

No abras un issue público. Usa el formulario privado de GitHub:
[Reportar una vulnerabilidad](https://github.com/Consterna/ModpackES/security/advisories/new).

Cuenta qué pasa, cómo reproducirlo y qué versión usas. La respuesta llega lo antes posible y, cuando esté
corregido, el reporte se publica con el crédito para quien lo encontró (si así lo quiere).

## Cómo maneja ModpackES tus datos

- La clave de Gemini se guarda en el Administrador de credenciales de Windows; nunca en un archivo ni en el
  registro de la ventana.
- Los textos a traducir se envían solo a la API de Gemini de Google.
- Todo lo demás (memoria de traducciones, glosario, preferencias) se queda en `%LOCALAPPDATA%\traductor-es`.
