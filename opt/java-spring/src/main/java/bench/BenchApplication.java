package bench;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/** Ponto de entrada do alvo Java, igual nas variantes JVM e Native Image. */
@SpringBootApplication
public class BenchApplication {

    public static void main(String[] args) {
        // Definidas antes do primeiro uso do HttpClient, que lê os valores uma única vez.
        // O padrão de 16 KiB por conexão pesa com milhares de chamadas paradas.
        System.setProperty("jdk.httpclient.bufsize", "2048");
        System.setProperty("jdk.httpclient.keepalive.timeout", "60");
        SpringApplication.run(BenchApplication.class, args);
    }
}
