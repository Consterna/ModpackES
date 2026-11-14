#!/bin/bash
# Sesiones en la nube: los commits van a nombre del dueño del repositorio.
# En este PC no hace nada; aquí manda el git config del usuario.

if [ "$CLAUDE_CODE_REMOTE" != "true" ]; then
  exit 0
fi

NOMBRE="Cristian"
CORREO="259780099+Consterna@users.noreply.github.com"

cd "$CLAUDE_PROJECT_DIR" || exit 0
git config user.name "$NOMBRE"
git config user.email "$CORREO"
git config --global user.name "$NOMBRE"
git config --global user.email "$CORREO"

# Las variables de entorno ganan a git config: se fijan también para el resto de la sesión.
if [ -n "$CLAUDE_ENV_FILE" ]; then
  {
    echo "export GIT_AUTHOR_NAME=$NOMBRE"
    echo "export GIT_AUTHOR_EMAIL=$CORREO"
    echo "export GIT_COMMITTER_NAME=$NOMBRE"
    echo "export GIT_COMMITTER_EMAIL=$CORREO"
  } >> "$CLAUDE_ENV_FILE"
fi

exit 0
