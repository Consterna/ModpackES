# Firma digital del ejecutable (SignPath)

El `.exe` se publica sin firma, así que Windows SmartScreen avisa la primera vez. La
[SignPath Foundation](https://signpath.org/) firma gratis proyectos de código abierto. El workflow de release
ya tiene el paso preparado: se activa solo cuando existen los datos de SignPath en el repositorio. Mientras
no estén, la release sale sin firmar, como ahora.

## 1. Pedir la firma

1. Revisa las condiciones en [signpath.org/terms](https://signpath.org/terms). Lo principal:
   - todo el proyecto es código abierto (ModpackES es GPL-3.0);
   - el ejecutable se construye en GitHub Actions desde el repositorio;
   - todos los que mantienen el proyecto usan verificación en dos pasos en GitHub y en SignPath;
   - la SignPath Foundation figura como editor del archivo firmado.
2. Envía la solicitud en [signpath.org/apply](https://signpath.org/apply.html) con el enlace al repositorio.

No sé cuánto tarda la aprobación ni si aceptan proyectos de una sola persona: depende de ellos.

## 2. Configurar SignPath

Cuando aprueben el proyecto, en SignPath:

1. Agrega el sistema de compilación de confianza **GitHub.com** a la organización y vincúlalo al proyecto.
2. Crea una configuración de artefacto cuya raíz sea un `<zip-file>` que contenga `ModpackES.exe` (el artefacto
   que sube el CI es un zip con ese archivo).
3. Crea una política de firma (por ejemplo `release-signing`) y un token de API para el CI.

Guía oficial: [docs.signpath.io/trusted-build-systems/github](https://docs.signpath.io/trusted-build-systems/github).

## 3. Configurar el repositorio

En GitHub → *Settings* → *Secrets and variables* → *Actions*:

| Tipo | Nombre | Valor |
|---|---|---|
| Secreto | `SIGNPATH_API_TOKEN` | El token de API de SignPath |
| Variable | `SIGNPATH_ORGANIZATION_ID` | El id de la organización |
| Variable | `SIGNPATH_PROJECT_SLUG` | El slug del proyecto (por ejemplo `ModpackES`) |
| Variable | `SIGNPATH_SIGNING_POLICY_SLUG` | El slug de la política (por ejemplo `release-signing`) |

Con eso, la próxima etiqueta `v*` publica el `.exe` firmado. La atestación y el SHA-256 se calculan sobre el
archivo ya firmado.

## 4. Atribución

Las condiciones piden mostrar este texto donde se ofrezca la descarga firmada; las notas de la release lo
agregan solas cuando hay firma:

> Free code signing provided by [SignPath.io](https://signpath.io), certificate by
> [SignPath Foundation](https://signpath.org).

**No probado:** este paso no se pudo probar sin una cuenta aprobada de SignPath. Si falla en la primera
release firmada, revisa el registro del job «Publicar la release».
