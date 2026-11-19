package io.github.consterna.modpackes.sonda;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DiscoTest {
    @Test
    void lasTareasCorrenEnOrdenEnUnSoloHilo() throws InterruptedException {
        List<String> hecho = new CopyOnWriteArrayList<>();
        List<String> hilos = new CopyOnWriteArrayList<>();
        try (Disco d = new Disco("prueba-disco", e -> { })) {
            for (int i = 0; i < 20; i++) {
                int n = i;
                d.enviar(() -> {
                    hecho.add("t" + n);
                    hilos.add(Thread.currentThread().getName());
                });
            }
        }
        assertEquals(20, hecho.size());
        assertEquals("t0", hecho.get(0));
        assertEquals("t19", hecho.get(19));
        assertTrue(hilos.stream().allMatch("prueba-disco"::equals));
    }

    @Test
    void unFalloSeAvisaYNoParaLoSiguiente() throws InterruptedException {
        List<Throwable> fallos = new CopyOnWriteArrayList<>();
        AtomicInteger despues = new AtomicInteger();
        try (Disco d = new Disco("prueba-disco", fallos::add)) {
            d.enviar(() -> {
                throw new IllegalStateException("roto");
            });
            d.enviar(despues::incrementAndGet);
        }
        assertEquals(1, fallos.size());
        assertEquals(1, despues.get());
    }

    @Test
    void laTareaPeriodicaSigueTrasUnFallo() throws InterruptedException {
        CountDownLatch vueltas = new CountDownLatch(2);
        AtomicInteger n = new AtomicInteger();
        try (Disco d = new Disco("prueba-disco", e -> { })) {
            d.cadaPocosSegundos(() -> {
                vueltas.countDown();
                if (n.incrementAndGet() == 1) {
                    throw new IllegalStateException("primera vuelta");
                }
            }, 1);
            assertTrue(vueltas.await(10, TimeUnit.SECONDS));
        }
    }
}
