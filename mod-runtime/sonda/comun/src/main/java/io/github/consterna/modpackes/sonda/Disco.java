package io.github.consterna.modpackes.sonda;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;

/**
 * Un solo hilo de fondo para todo lo que va a disco, así dos volcados nunca escriben a la vez y el juego no espera.
 * Corre una tarea periódica cada pocos segundos y la última vez al cerrarse la JVM.
 */
public final class Disco implements AutoCloseable {
    private final ScheduledExecutorService hilo;
    private final Consumer<Throwable> alFallar;

    public Disco(String nombre, Consumer<Throwable> alFallar) {
        this.alFallar = alFallar;
        this.hilo = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, nombre);
            t.setDaemon(true); // no impide que el juego se cierre
            return t;
        });
    }

    /** Corre {@code tarea} cada {@code segundos} y una vez más cuando se cierra la JVM. */
    public void cadaPocosSegundos(Runnable tarea, long segundos) {
        hilo.scheduleWithFixedDelay(protegida(tarea), segundos, segundos, TimeUnit.SECONDS);
        Runtime.getRuntime().addShutdownHook(new Thread(protegida(tarea), "modpackes-sonda-cierre"));
    }

    /** Corre {@code tarea} en el hilo de fondo en cuanto pueda. */
    public void enviar(Runnable tarea) {
        hilo.execute(protegida(tarea));
    }

    /** Espera a que acabe lo enviado (para pruebas) y apaga el hilo. */
    @Override
    public void close() throws InterruptedException {
        ExecutorService h = hilo;
        h.shutdown();
        h.awaitTermination(30, TimeUnit.SECONDS);
    }

    /** Un fallo se avisa y no corta la tarea periódica (un {@code scheduleWithFixedDelay} se para si una vuelta lanza). */
    private Runnable protegida(Runnable tarea) {
        return () -> {
            try {
                tarea.run();
            } catch (RuntimeException | LinkageError e) {
                alFallar.accept(e);
            }
        };
    }
}
