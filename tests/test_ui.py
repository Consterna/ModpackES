"""La ventana sin pantalla (Qt offscreen) y la exportación."""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pytestqt.qtbot import QtBot

from traductor_es.fuentes import vanilla
from traductor_es.fuentes.lanzadores import InstanciaEncontrada
from traductor_es.motores.base import Motor
from traductor_es.motores.simulador import Simulador
from traductor_es.salida import exportar
from traductor_es.ui.app import main
from traductor_es.ui.ventana import FabricaMotor, Ventana

from . import fabrica


@pytest.fixture(autouse=True)
def _entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    def ninguna() -> list[Path]:
        return []

    monkeypatch.setattr(vanilla, "raices_de_lanzadores", ninguna)
    monkeypatch.setenv("TRADUCTOR_ES_PRUEBA_UI", "1")  # sin cuadros de diálogo


def siempre(motor: Motor) -> FabricaMotor:
    """Una fábrica que devuelve siempre el mismo motor, sea cual sea el elegido en la ventana."""

    def crear(_motor: str, _clave: str | None, _modelo: str, _direccion: str) -> Motor:
        return motor

    return crear


def _modpack(tmp_path: Path) -> Path:
    juego = fabrica.prism(tmp_path, "1.20.1")
    fabrica.jar(juego / "mods" / "m.jar", fabrica.lang("m", "en_us", {"item.m.wrench": "Wrench"}))
    capitulo = juego / "config" / "ftbquests" / "quests" / "chapters" / "a.snbt"
    capitulo.parent.mkdir(parents=True)
    capitulo.write_text('{ title: "Getting Started" }', encoding="utf-8")
    script = juego / "kubejs" / "server_scripts" / "s.js"
    script.parent.mkdir(parents=True)
    script.write_text("player.tell('Welcome to the pack')\n", encoding="utf-8")
    fabrica.opciones(juego, ["vanilla"], "en_us")
    return juego


def _ventana(qtbot: QtBot, juego: Path) -> Ventana:
    def instancias() -> list[InstanciaEncontrada]:
        return [InstanciaEncontrada("Prism Launcher", "Prueba", juego)]

    def simulador(_motor: str, _clave: str | None, _modelo: str, _direccion: str) -> Motor:
        return Simulador()

    v = Ventana(buscar_instancias=instancias, fabrica_motor=simulador)
    qtbot.addWidget(v)
    v.lista.setCurrentRow(0)
    return v


def _analizar(qtbot: QtBot, v: Ventana) -> None:
    """Como el jugador: el botón principal, o «Analizar de nuevo» si la instancia ya se tradujo."""
    (v.b_principal if v.b_secundario.isHidden() else v.b_secundario).click()
    qtbot.waitUntil(
        lambda: v._hilo is None and v.b_principal.text().startswith(("Traducir", "Aplicar")),  # pyright: ignore[reportPrivateUsage]
        timeout=30000,
    )


def _traducir(qtbot: QtBot, v: Ventana) -> None:
    _analizar(qtbot, v)
    v.b_principal.click()
    qtbot.waitUntil(lambda: v._hilo is None and "Listo" in v.estado.text(), timeout=30000)  # pyright: ignore[reportPrivateUsage]


def test_analizar_traducir_y_restaurar(qtbot: QtBot, tmp_path: Path) -> None:
    juego = _modpack(tmp_path)
    v = _ventana(qtbot, juego)
    assert v.lista.count() == 1 and v.carpeta() == str(juego)
    v.b_principal.click()
    qtbot.waitUntil(lambda: v._hilo is None and v.ultimo_informe is not None, timeout=30000)  # pyright: ignore[reportPrivateUsage]
    assert v.grupos["libros"].e_detalle.text() == "No hay en esta instancia"
    assert all(v.grupos[g].e_numero.text() != "—" for g in ("mods", "misiones", "scripts"))
    assert "Costo estimado" in v.costo.text() and v.b_principal.text().startswith(("Traducir", "Aplicar"))
    assert not (juego / "resourcepacks").exists()  # analizar no escribe
    v.b_principal.click()
    qtbot.waitUntil(lambda: v._hilo is None and "Listo" in v.estado.text(), timeout=30000)  # pyright: ignore[reportPrivateUsage]
    actual = v.lista.actual()
    assert v.b_principal.text() == "Listo: abrir la carpeta" and actual is not None and actual.traducida
    assert "«ES» Welcome to the pack" in (juego / "kubejs" / "server_scripts" / "s.js").read_text("utf-8")
    assert (juego / "resourcepacks" / "Traduccion_ES" / "pack.mcmeta").is_file()
    assert "lang:es_mx" in (juego / "options.txt").read_text("utf-8")
    v.a_restaurar.trigger()
    qtbot.waitUntil(lambda: v._hilo is None and "Restaurados" in v.estado.text(), timeout=30000)  # pyright: ignore[reportPrivateUsage]
    assert (juego / "kubejs" / "server_scripts" / "s.js").read_text("utf-8") == "player.tell('Welcome to the pack')\n"
    assert v.b_principal.text() == "Analizar (gratis)" and v.ultimo_informe is None


def test_sin_instancia_avisa(qtbot: QtBot) -> None:
    v = Ventana(buscar_instancias=list)
    qtbot.addWidget(v)
    v.b_principal.click()
    assert "Elige primero una instancia" in v.log.toPlainText() and not v.aviso.isHidden()


def test_error_se_muestra_y_libera_la_ventana(qtbot: QtBot, tmp_path: Path) -> None:
    def rota() -> list[InstanciaEncontrada]:
        return [InstanciaEncontrada("Prism Launcher", "Rota", tmp_path / "no-existe")]

    v = Ventana(buscar_instancias=rota)
    qtbot.addWidget(v)
    v.lista.setCurrentRow(0)
    v.b_principal.click()
    qtbot.waitUntil(lambda: v._hilo is None and "Se detuvo" in v.estado.text(), timeout=30000)  # pyright: ignore[reportPrivateUsage]
    assert "No encuentro" in v.log.toPlainText() and v.b_principal.isEnabled() and v.detalles.abierta
    assert v.b_principal.text() == "Analizar (gratis)" and v.aviso.tipo == "error"


def test_exportar_pack_y_kit(tmp_path: Path) -> None:
    juego = _modpack(tmp_path)
    with pytest.raises(ValueError):
        exportar.exportar_pack(juego, tmp_path / "x.zip")
    assert main(["--autoprueba", str(juego), str(tmp_path / "auto.json")]) == 0
    datos = json.loads((tmp_path / "auto.json").read_text("utf-8"))
    assert datos["icono"] is True
    assert datos["minecraft"] == "1.20.1" and {m["grupo"] for m in datos["modulos"]} == {"mods", "misiones", "scripts"}
    from traductor_es.__main__ import main as cli

    assert cli(["traducir", str(juego), "--simular"]) == 0
    n = exportar.exportar_pack(juego, tmp_path / "Traduccion_ES.zip")
    with zipfile.ZipFile(tmp_path / "Traduccion_ES.zip") as z:
        assert "pack.mcmeta" in z.namelist() and n == len(z.namelist())
    exportar.exportar_kit_servidor(juego, tmp_path / "kit.zip")
    with zipfile.ZipFile(tmp_path / "kit.zip") as z:
        nombres = set(z.namelist())
        assert {"LEEME.txt", "Traduccion_ES.zip", "config/ftbquests/quests/chapters/a.snbt"} <= nombres
        assert "kubejs/server_scripts/s.js" in nombres
        assert "«ES» Getting Started" in z.read("config/ftbquests/quests/chapters/a.snbt").decode("utf-8")


def test_probar_clave_no_congela_y_muestra_modelos(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from traductor_es import configuracion
    from traductor_es.motores.gemini import Gemini

    monkeypatch.setattr(configuracion, "leer_clave", lambda _motor="gemini": "clave")
    modelos = SimpleNamespace(
        list=lambda: [SimpleNamespace(name="models/gemini-9-flash", supported_actions=["generateContent"])]
    )

    def fabrica(_motor: str, clave: str | None, modelo: str, _direccion: str) -> Motor:
        return Gemini(clave or "", modelo, cliente=SimpleNamespace(models=modelos))

    v = Ventana(buscar_instancias=list, fabrica_motor=fabrica)
    qtbot.addWidget(v)
    v.b_probar.click()
    qtbot.waitUntil(lambda: "modelos disponibles" in v.log.toPlainText(), timeout=10000)
    assert [v.c_modelo.itemText(i) for i in range(v.c_modelo.count())] == ["gemini-9-flash"]
    assert v.b_probar.isEnabled()


def test_proceso_conecta_cancelar_y_espera_al_motor(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from traductor_es.motores.gemini import Gemini
    from traductor_es.proceso import Proceso

    juego = _modpack(tmp_path)
    mensajes: list[str] = []
    motor = Gemini("clave", cliente=SimpleNamespace())
    with Proceso(juego, motor, registro=mensajes.append) as p:
        assert motor.cancelar is p.traductor.cancelar
    motor.al_esperar("JOB_STATE_RUNNING")
    assert mensajes[-1] == "Esperando a Google (Batch API): procesando"


def test_cambiar_de_instancia_borra_el_analisis_anterior(qtbot: QtBot, tmp_path: Path) -> None:
    juego = _modpack(tmp_path / "a")
    otro = _modpack(tmp_path / "b")

    def instancias() -> list[InstanciaEncontrada]:
        return [InstanciaEncontrada("Prism Launcher", "A", juego), InstanciaEncontrada("Prism Launcher", "B", otro)]

    v = Ventana(buscar_instancias=instancias)
    qtbot.addWidget(v)
    v.lista.setCurrentRow(0)
    v.b_principal.click()
    qtbot.waitUntil(lambda: v._hilo is None and v.ultimo_informe is not None, timeout=30000)  # pyright: ignore[reportPrivateUsage]
    v.lista.setCurrentRow(1)
    assert v.ultimo_informe is None and v.costo.text() == "" and v.b_principal.text() == "Analizar (gratis)"
    assert all(t.e_numero.text() == "—" for t in v.grupos.values())


def test_error_no_previsto_libera_la_ventana_y_queda_en_el_registro(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from traductor_es import registro
    from traductor_es.proceso import Proceso

    def romper(_self: Proceso) -> None:
        raise RuntimeError("fallo inventado")

    monkeypatch.setattr(Proceso, "analizar", romper)
    ruta = registro.configurar(tmp_path / "datos")
    try:
        v = _ventana(qtbot, _modpack(tmp_path))
        v.b_principal.click()
        qtbot.waitUntil(lambda: v._hilo is None and "Se detuvo" in v.estado.text(), timeout=30000)  # pyright: ignore[reportPrivateUsage]
        assert v.b_principal.isEnabled() and "Error no previsto: RuntimeError: fallo inventado" in v.log.toPlainText()
        texto = v.copiar_diagnostico()
        from PySide6.QtWidgets import QApplication

        assert QApplication.clipboard().text() == texto and "fallo inventado" in texto and "Instancia:" in texto
        assert "Traceback" in ruta.read_text(encoding="utf-8")
    finally:
        registro.cerrar()


def test_corregir_desde_la_ventana_y_volver_a_traducir_sin_pagar(qtbot: QtBot, tmp_path: Path) -> None:
    from traductor_es import configuracion
    from traductor_es.nucleo.memoria import Memoria
    from traductor_es.ui.correcciones import DialogoCorrecciones

    juego = _modpack(tmp_path)
    motor = Simulador()
    v = Ventana(
        buscar_instancias=lambda: [InstanciaEncontrada("Prism Launcher", "P", juego)],
        fabrica_motor=siempre(motor),
    )
    qtbot.addWidget(v)
    v.lista.setCurrentRow(0)
    _traducir(qtbot, v)
    enviados = sum(len(lote.entradas) for lote in motor.lotes_recibidos)

    with Memoria(configuracion.ruta_memoria()) as memoria:
        d = DialogoCorrecciones("es_mx", memoria)
        qtbot.addWidget(d)
        d.e_buscar.setText("welcome")
        d.buscar()
        assert [c.origen for c in d.resultados] == ["Welcome to the pack"]
        assert not d.b_guardar.isEnabled()  # sin fila elegida no se puede guardar
        d.tabla.setCurrentCell(0, 0)
        assert d.b_guardar.isEnabled() and not d.b_quitar.isEnabled()
        d.t_correccion.setPlainText("Te damos la bienvenida %s")
        d.guardar()
        assert "códigos" in d.estado.text()  # inventó un código: se rechaza
        d.t_correccion.setPlainText("Te damos la bienvenida al pack")
        d.guardar()
        assert d.resultados[0].corregida and d.b_quitar.isEnabled()
        d.e_buscar.clear()
        d.buscar()
        assert [c.traduccion for c in d.resultados] == ["Te damos la bienvenida al pack"]

    _traducir(qtbot, v)
    assert sum(len(lote.entradas) for lote in motor.lotes_recibidos) == enviados  # no se pidió nada nuevo
    script = (juego / "kubejs" / "server_scripts" / "s.js").read_text("utf-8")
    assert script == "player.tell('Te damos la bienvenida al pack')\n"


def test_la_ambientacion_se_guarda_por_instancia(qtbot: QtBot, tmp_path: Path) -> None:
    from traductor_es import configuracion

    a, b = _modpack(tmp_path / "a"), _modpack(tmp_path / "b")
    # Un texto que ninguna otra prueba tradujo, para que vaya al motor y no salga de la memoria
    (a / "kubejs" / "server_scripts" / "s.js").write_text("player.tell('Harvest the golden wheat')\n", "utf-8")
    motor = Simulador()

    def instancias() -> list[InstanciaEncontrada]:
        return [InstanciaEncontrada("Prism Launcher", "A", a), InstanciaEncontrada("Prism Launcher", "B", b)]

    v = Ventana(buscar_instancias=instancias, fabrica_motor=siempre(motor))
    qtbot.addWidget(v)
    v.lista.setCurrentRow(0)
    v.e_contexto.setText("Granja acogedora")
    _traducir(qtbot, v)
    assert motor.lotes_recibidos and all(lote.contexto == "Granja acogedora" for lote in motor.lotes_recibidos)
    assert configuracion.leer_preferencias()["contextos"] == {str(a): "Granja acogedora"}
    v.lista.setCurrentRow(1)
    assert v.e_contexto.text() == ""
    v.lista.setCurrentRow(0)
    assert v.e_contexto.text() == "Granja acogedora"


def test_un_grupo_desmarcado_no_se_traduce_ni_se_cobra(qtbot: QtBot, tmp_path: Path) -> None:
    from traductor_es import configuracion

    antes = configuracion.leer_preferencias()
    juego = _modpack(tmp_path)
    (juego / "kubejs" / "server_scripts" / "s.js").write_text("player.tell('Never translate this one')\n", "utf-8")
    try:
        v = _ventana(qtbot, juego)
        _analizar(qtbot, v)
        assert v.grupos["scripts"].e_numero.text() == "1"
        con_scripts = v.b_principal.text()
        v.grupos["scripts"].fijar_incluido(False)
        assert v.b_principal.text() != con_scripts and not v.grupos["scripts"].activa
        for g in ("mods", "libros", "misiones"):
            v.grupos[g].fijar_incluido(False)
        assert not v.b_principal.isEnabled() and "Marca al menos" in v.b_principal.text()
        v.grupos["misiones"].fijar_incluido(True)
        v.b_principal.click()
        qtbot.waitUntil(lambda: v._hilo is None and "Listo" in v.estado.text(), timeout=30000)  # pyright: ignore[reportPrivateUsage]
        assert "Never translate" in (juego / "kubejs" / "server_scripts" / "s.js").read_text("utf-8")
        capitulo = juego / "config" / "ftbquests" / "quests" / "chapters" / "a.snbt"
        assert "«ES» Getting Started" in capitulo.read_text("utf-8")
        assert configuracion.leer_preferencias()["grupos"] == ["misiones"]
    finally:
        configuracion.guardar_preferencias(antes)  # las demás pruebas abren la ventana con todos los grupos


def test_las_tarjetas_muestran_version_loader_y_estado(qtbot: QtBot, tmp_path: Path) -> None:
    v = _ventana(qtbot, _modpack(tmp_path))
    actual = v.lista.actual()
    assert actual is not None
    qtbot.waitUntil(lambda: "1.20.1" in actual.e_detalle.text(), timeout=10000)
    assert actual.e_detalle.text() == "1.20.1 · Forge · Prism Launcher" and actual.traducida is False
    assert v.e_titulo.text() == "Prueba" and str(tmp_path) in v.e_ruta.texto_completo()


def test_elegir_el_tema_lo_aplica_y_lo_recuerda(qtbot: QtBot) -> None:
    from traductor_es import configuracion
    from traductor_es.ui import tema

    v = Ventana(buscar_instancias=list)
    qtbot.addWidget(v)
    instalado = tema.tema()
    assert instalado is not None
    try:
        v.a_temas["claro"].trigger()
        assert tema.actual() is tema.CLARO and configuracion.leer_preferencias()["tema"] == "claro"
        v.a_temas["oscuro"].trigger()
        assert tema.actual() is tema.OSCURO and v.a_temas["oscuro"].isChecked()
    finally:
        v.elegir_tema("sistema")


def test_el_estado_del_motor_se_ve_arriba(qtbot: QtBot) -> None:
    v = Ventana(buscar_instancias=list)
    qtbot.addWidget(v)
    v.c_motor.setCurrentIndex(v.c_motor.findData("gemini"))
    assert v.b_motor.text() == "Gemini · falta la clave" and v.pasos.estado(0) == "actual"
    v.c_motor.setCurrentIndex(v.c_motor.findData("lmstudio"))
    assert v.b_motor.text() == "LM Studio · listo" and v.pasos.estado(0) == "hecho"
    assert "LM Studio" in v.dialogo_motor.guia.text()
    v.abrir_motor()
    assert v.dialogo_motor.isVisible()
    v.dialogo_motor.reject()
    v.c_motor.setCurrentIndex(v.c_motor.findData("gemini"))


def test_bienvenida_la_primera_vez(qtbot: QtBot) -> None:
    from traductor_es import configuracion

    antes = configuracion.leer_preferencias()
    try:
        configuracion.guardar_preferencias({})
        v = Ventana(buscar_instancias=list)
        qtbot.addWidget(v)
        assert not v.bienvenida.isHidden()
        v.bienvenida.b_configurar.click()
        assert v.dialogo_motor.isVisible()
        v.dialogo_motor.reject()
        v.bienvenida.b_entendido.click()
        assert v.bienvenida.isHidden() and configuracion.leer_preferencias()["bienvenida_vista"] is True
        otra = Ventana(buscar_instancias=list)
        qtbot.addWidget(otra)
        assert otra.bienvenida.isHidden()
    finally:
        configuracion.guardar_preferencias(antes)


def test_preferencias_danadas_no_impiden_abrir(qtbot: QtBot) -> None:
    from traductor_es import configuracion

    configuracion.guardar_preferencias({"hilos": "muchos", "grupos": 7, "contextos": [1], "modelos": "x"})
    v = Ventana(buscar_instancias=list)
    qtbot.addWidget(v)
    assert v.c_hilos.value() == 4 and all(t.incluido for t in v.grupos.values())


def test_cerrar_espera_a_probar_conexion(qtbot: QtBot) -> None:
    import threading

    soltar = threading.Event()

    class Lento(Simulador):
        def listar_modelos(self) -> list[str]:
            soltar.wait(0.3)
            return ["modelo"]

    v = Ventana(buscar_instancias=list, fabrica_motor=siempre(Lento()))
    qtbot.addWidget(v)
    v.b_probar.click()
    sondeo = v._sondeo  # pyright: ignore[reportPrivateUsage]
    assert sondeo is not None and sondeo.isRunning()
    v.close()
    assert not sondeo.isRunning()


def test_cerrar_con_conexion_bloqueada_espera_a_que_termine(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Si la prueba no contesta a tiempo, la ventana se oculta y se cierra recién cuando el hilo termina."""
    import threading

    from PySide6.QtGui import QCloseEvent

    soltar = threading.Event()

    class Colgado(Simulador):
        def listar_modelos(self) -> list[str]:
            soltar.wait(10)
            return ["modelo"]

    class Registra(Ventana):
        aceptado = False

        def closeEvent(self, event: QCloseEvent) -> None:
            super().closeEvent(event)
            self.aceptado = event.isAccepted()

    monkeypatch.setattr(Ventana, "ESPERA_AL_CERRAR_MS", 50)
    v = Registra(buscar_instancias=list, fabrica_motor=siempre(Colgado()))
    qtbot.addWidget(v)
    v.show()
    v.b_probar.click()
    sondeo = v._sondeo  # pyright: ignore[reportPrivateUsage]
    assert sondeo is not None
    assert v.close() is False  # todavía no: el hilo sigue vivo
    assert sondeo.isRunning() and v.isHidden() and not v.aceptado
    soltar.set()  # desde aquí el QThread puede estar ya borrado (deleteLater): no se le pregunta nada
    qtbot.waitUntil(lambda: v.aceptado and v._sondeo is None, timeout=10000)  # pyright: ignore[reportPrivateUsage]


def test_soltar_la_carpeta_de_un_modpack(qtbot: QtBot, tmp_path: Path) -> None:
    from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
    from PySide6.QtGui import QDropEvent

    juego = _modpack(tmp_path)
    suelta = tmp_path / "suelta.txt"
    suelta.write_text("x", encoding="utf-8")
    v = Ventana(buscar_instancias=list)
    qtbot.addWidget(v)
    datos = QMimeData()
    datos.setUrls([QUrl.fromLocalFile(str(juego)), QUrl.fromLocalFile(str(suelta)), QUrl("https://example.com")])
    assert v.carpetas_soltadas(datos) == [str(juego)]
    v.dropEvent(QDropEvent(QPointF(5, 5), Qt.DropAction.CopyAction, datos, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier))  # fmt: skip
    actual = v.lista.actual()
    assert v.lista.count() == 1 and v.carpeta() == str(juego) and actual is not None and actual.nombre == "Pack"
    assert not v.agregar_carpeta(str(tmp_path)) and "no parece una instancia" in v.aviso.e_texto.text()
    assert v.lista.count() == 1


def test_atajos_de_teclado(qtbot: QtBot) -> None:
    v = Ventana(buscar_instancias=list)
    qtbot.addWidget(v)
    assert {a.key().toString() for a in v.atajos} == {"Ctrl+F", "F5", "Ctrl+Return", "Ctrl+Enter"}


def test_la_misma_carpeta_con_otras_barras_no_se_repite(qtbot: QtBot, tmp_path: Path) -> None:
    juego = _modpack(tmp_path)
    v = _ventana(qtbot, juego)
    assert v.agregar_carpeta(str(juego).replace("\\", "/"))
    assert v.lista.count() == 1 and v.carpeta() == str(juego)


def test_cancelar_no_se_muestra_como_error(qtbot: QtBot) -> None:
    v = Ventana(buscar_instancias=list)
    qtbot.addWidget(v)
    v._cancelar.set()  # pyright: ignore[reportPrivateUsage]
    v._fallar("Cancelado. Lo traducido hasta ahora quedó guardado en la memoria.")  # pyright: ignore[reportPrivateUsage]
    assert v.aviso.tipo == "info" and not v.detalles.abierta and v.estado.text() == "Se detuvo."


def test_f5_y_el_motor_no_se_tocan_mientras_trabaja(qtbot: QtBot, tmp_path: Path) -> None:
    from PySide6.QtCore import QThread

    v = _ventana(qtbot, _modpack(tmp_path))
    tarjeta = v.lista.actual()
    v._hilo = QThread(v)  # pyright: ignore[reportPrivateUsage]
    v._estado = "trabajando"  # pyright: ignore[reportPrivateUsage]
    v._ocupado(True)  # pyright: ignore[reportPrivateUsage]
    try:
        v.actualizar_instancias()
        assert v.lista.actual() is tarjeta and not v.b_cancelar.isHidden()
        assert not v.a_motor.isEnabled() and not v.bienvenida.b_configurar.isEnabled()
    finally:
        v._hilo = None  # pyright: ignore[reportPrivateUsage]
        v._estado = "analizar"  # pyright: ignore[reportPrivateUsage]
        v._ocupado(False)  # pyright: ignore[reportPrivateUsage]
    assert v.a_motor.isEnabled()


def test_soltar_la_carpeta_de_la_instancia_no_la_repite(qtbot: QtBot, tmp_path: Path) -> None:
    juego = _modpack(tmp_path)
    v = _ventana(qtbot, juego)  # el lanzador la da como …/Pack/minecraft
    assert v.agregar_carpeta(str(juego.parent))  # se suelta …/Pack
    assert v.lista.count() == 1 and v.carpeta() == str(juego)


def test_un_grupo_que_no_se_puede_leer_queda_fuera(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from traductor_es.modulos import scripts
    from traductor_es.proceso import Proceso

    def romper(_self: object) -> list[object]:
        raise OSError("archivo bloqueado")

    monkeypatch.setattr(scripts.ScriptsKubeJS, "recolectar", romper)
    juego = _modpack(tmp_path)
    with Proceso(juego, Simulador()) as p:
        informe = p.analizar()
    assert informe.fallidos == ["scripts"] and any("archivo bloqueado" in a for a in informe.avisos)
    assert {m.grupo for m in informe.modulos} == {"mods", "misiones"}
    v = _ventana(qtbot, juego)
    _analizar(qtbot, v)
    assert not v.grupos["scripts"].incluido and "No se pudo leer" in v.grupos["scripts"].e_detalle.text()
    assert v.b_principal.isEnabled()


def test_que_queda_en_ingles_solo_lee(qtbot: QtBot, tmp_path: Path) -> None:
    juego = _modpack(tmp_path)
    ruta = juego / "kubejs" / "server_scripts" / "s.js"
    ruta.write_text(
        ruta.read_text("utf-8") + "\nlet nota = 'This sentence looks like a message but is not used'\n",
        encoding="utf-8",
    )
    antes = ruta.read_bytes()
    v = _ventana(qtbot, juego)
    v.a_cobertura.trigger()
    qtbot.waitUntil(lambda: v._hilo is None and "lugares" in v.estado.text(), timeout=30000)  # pyright: ignore[reportPrivateUsage]
    assert "This sentence looks like a message" in v.log.toPlainText()
    assert ruta.read_bytes() == antes and not (juego / "resourcepacks").exists()  # solo lee
    assert v.b_principal.isEnabled()  # el botón principal sigue disponible


def test_sin_instancia_elegida_no_lanza_nada(qtbot: QtBot, tmp_path: Path) -> None:
    v = Ventana(buscar_instancias=lambda: [], fabrica_motor=siempre(Simulador()))
    qtbot.addWidget(v)
    v.lanzar("analizar")
    v.a_cobertura.trigger()
    assert v._hilo is None and v.carpeta() is None  # pyright: ignore[reportPrivateUsage]


def test_instancia_sin_version_detectable_se_recupera(qtbot: QtBot, tmp_path: Path) -> None:
    juego = tmp_path / "Pack" / "minecraft"
    (juego / "mods").mkdir(parents=True)  # sin lanzador, sin log y sin mods con versión
    v = _ventana(qtbot, juego)
    v.b_principal.click()
    qtbot.waitUntil(lambda: v._hilo is None and "Se detuvo" in v.estado.text(), timeout=30000)  # pyright: ignore[reportPrivateUsage]
    assert v.b_principal.isEnabled() and "Traceback" not in v.log.toPlainText()


def test_cobertura_sin_nada_que_decir(qtbot: QtBot, tmp_path: Path) -> None:
    juego = fabrica.prism(tmp_path, "1.20.1")
    fabrica.jar(juego / "mods" / "m.jar", fabrica.lang("m", "en_us", {"item.m.a": "Iron Plate"}))
    v = _ventana(qtbot, juego)
    v.a_cobertura.trigger()
    qtbot.waitUntil(lambda: v._hilo is None and "No encontré" in v.estado.text(), timeout=30000)  # pyright: ignore[reportPrivateUsage]


def test_soltar_rutas_que_no_son_carpetas(qtbot: QtBot, tmp_path: Path) -> None:
    from PySide6.QtCore import QMimeData, QUrl

    archivo = tmp_path / "x.txt"
    archivo.write_text("x", encoding="utf-8")
    datos = QMimeData()
    datos.setUrls(
        [QUrl.fromLocalFile(str(archivo)), QUrl.fromLocalFile(str(tmp_path / "no_existe")), QUrl("https://x.y/z")]
    )
    assert Ventana.carpetas_soltadas(datos) == []
    datos.setUrls([QUrl.fromLocalFile(str(tmp_path))])
    assert Ventana.carpetas_soltadas(datos) == [str(tmp_path)]


def test_opcion_de_texto_java_y_mod_de_apoyo_en_la_ventana(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from traductor_es.salida import mod_apoyo

    vacia = tmp_path / "sin_jars"
    vacia.mkdir()
    monkeypatch.setattr(mod_apoyo, "_carpeta_de_jars", lambda: vacia)  # sin importar si esta copia ya compiló el jar
    juego = _modpack(tmp_path)
    v = _ventana(qtbot, juego)
    assert not v.c_java.isChecked() and v.opciones()["texto_java"] is False  # apagada por defecto
    v.c_java.setChecked(True)
    assert v.opciones()["texto_java"] is True
    v.a_apoyo.trigger()  # Forge 1.20.1 sí tiene mod de apoyo, pero sin el jar empaquetado debe avisar, no romper
    assert "no trae el mod de apoyo" in v.aviso.e_texto.text()
    assert not list((juego / "mods").glob("modpackes_runtime-*.jar"))
    v.a_quitar_apoyo.trigger()
    assert "No había mod de apoyo" in v.aviso.e_texto.text()


def test_informe_en_cuadro_y_guardado_en_archivo(qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    juego = _modpack(tmp_path)
    ruta = juego / "kubejs" / "server_scripts" / "s.js"
    ruta.write_text(
        ruta.read_text("utf-8") + "\nlet nota = 'This sentence looks like a message but is not used'\n",
        encoding="utf-8",
    )
    v = _ventana(qtbot, juego)
    v.guardar_informe_en(str(tmp_path / "antes.txt"))
    assert not (tmp_path / "antes.txt").exists()  # todavía no hay informe: no escribe nada
    v.a_cobertura.trigger()
    qtbot.waitUntil(lambda: v._hilo is None and v._dialogo_informe is not None, timeout=30000)  # pyright: ignore[reportPrivateUsage]
    assert "This sentence looks like a message" in v._dialogo_informe.texto.toPlainText()  # pyright: ignore[reportPrivateUsage, reportOptionalMemberAccess]
    destino = tmp_path / "informe.txt"
    from PySide6.QtWidgets import QFileDialog

    def elegir(*_a: object, **_k: object) -> tuple[str, str]:
        return str(destino), ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(elegir))
    v._dialogo_informe.b_guardar.click()  # pyright: ignore[reportPrivateUsage, reportOptionalMemberAccess]
    assert "This sentence looks like a message" in destino.read_text("utf-8")  # el botón del cuadro guarda
    destino.unlink()
    v.a_guardar_informe.trigger()  # y la entrada del menú «Más» también
    assert "This sentence looks like a message" in destino.read_text("utf-8")
    v.a_comprobar_apoyo.trigger()
    assert "mod de apoyo" in v.aviso.e_texto.text().lower() or "mod de apoyo" in v.log.toPlainText().lower()


def test_paquete_e_importar_desde_el_menu(qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtWidgets import QFileDialog

    from traductor_es import configuracion
    from traductor_es.nucleo.memoria import Memoria

    juego = _modpack(tmp_path / "a")
    with Memoria(configuracion.ruta_memoria()) as memoria:
        memoria.guardar({"Wrench": "Llave inglesa"}, "es_mx", "ui", "gemini:x")
    elegido = {"ruta": str(tmp_path / "compartir.zip")}  # el diálogo puede devolverlo sin la extensión doble

    def elegir(*_a: object, **_k: object) -> tuple[str, str]:
        return elegido["ruta"], ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(elegir))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(elegir))
    v = _ventana(qtbot, juego)
    v.a_paquete.trigger()
    qtbot.waitUntil(lambda: v._hilo is None and "Paquete guardado" in v.estado.text(), timeout=30000)  # pyright: ignore[reportPrivateUsage]
    compartido = tmp_path / "compartir.modpackes.zip"
    assert compartido.is_file()
    configuracion.ruta_memoria().unlink()  # quien lo recibe no tiene nada traducido

    otra = _modpack(tmp_path / "b")
    lang = otra / "resourcepacks" / "Traduccion_ES" / "assets" / "m" / "lang" / "es_mx.json"
    v2 = _ventana(qtbot, otra)
    elegido["ruta"] = str(compartido)
    v2.a_importar.trigger()
    qtbot.waitUntil(lambda: v2._hilo is None and lang.is_file(), timeout=30000)  # pyright: ignore[reportPrivateUsage]
    assert json.loads(lang.read_text("utf-8"))["item.m.wrench"] == "Llave inglesa"
    assert "Importado (paquete): 1 traducción" in v2.log.toPlainText()
    # La misión y el script no venían en el paquete: no se dice «ya está en español»
    assert "Importado en parte" in v2.estado.text() and v2.aviso.tipo == "aviso"
    assert v2.b_principal.text().startswith("Traducir")

    elegido["ruta"] = str(tmp_path / "publicar.zip")
    v2.a_exportar.trigger()
    with zipfile.ZipFile(tmp_path / "publicar.zip") as z:
        leeme = z.read("LEEME.txt").decode("utf-8")
        assert "pack.png" in z.namelist()
    assert "gemini (x)" in leeme and "Una persona la revisó" in leeme


def test_analizar_otra_vez_muestra_que_cambio(qtbot: QtBot, tmp_path: Path) -> None:
    """Tras una traducción, el análisis dice qué cambió en el modpack desde entonces (sin rediseñar la pantalla)."""
    juego = _modpack(tmp_path)
    v = _ventana(qtbot, juego)
    _analizar(qtbot, v)
    assert "Desde la última traducción" not in v.costo.text()  # nunca se tradujo: no hay con qué comparar
    v.b_principal.click()
    qtbot.waitUntil(lambda: v._hilo is None and "Listo" in v.estado.text(), timeout=30000)  # pyright: ignore[reportPrivateUsage]
    fabrica.jar(juego / "mods" / "m.jar", fabrica.lang("m", "en_us", {"item.m.wrench": "Wrench", "item.m.x": "Drill"}))
    _analizar(qtbot, v)
    assert "Desde la última traducción" in v.costo.text() and "1 nuevas, 0 cambiadas, 0 borradas" in v.costo.text()


def test_la_version_de_espana_solo_con_otro_dialecto(qtbot: QtBot) -> None:
    v = Ventana(buscar_instancias=list)
    qtbot.addWidget(v)
    v.c_espana.setChecked(True)
    v.c_dialecto.setCurrentIndex(v.c_dialecto.findData("es_mx"))
    assert v.c_espana.isEnabled() and v.opciones()["tambien_es_es"]
    v.c_dialecto.setCurrentIndex(v.c_dialecto.findData("es_es"))
    assert not v.c_espana.isEnabled() and not v.opciones()["tambien_es_es"]
