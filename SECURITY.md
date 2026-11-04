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
- Los textos a traducir se envían solo al motor que elijas (Gemini, otro proveedor o un servidor en tu PC).
- Al abrirse, la app pregunta a la API pública de GitHub cuál es la última versión, sin datos tuyos; se
  puede desactivar. No descarga ni instala nada por su cuenta.
- Todo lo demás (memoria de traducciones, glosario, preferencias y `registro.log`) se queda en
  `%LOCALAPPDATA%\traductor-es`. El registro tapa la clave y cualquier texto con forma de clave de API, y
  «Copiar diagnóstico» cambia además tu carpeta personal por `~`.
