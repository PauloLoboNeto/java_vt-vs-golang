package bench;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/** Ponto de entrada do alvo Java, igual nas variantes JVM e Native Image. */
@SpringBootApplication
public class BenchApplication {

    public static void main(String[] args) {
        SpringApplication.run(BenchApplication.class, args);
    }
}
