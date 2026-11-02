package bench;

import java.net.http.HttpClient;
import java.time.Duration;
import java.util.concurrent.Executors;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

/** Configura o cliente da API externa, com bloqueio barato em virtual threads. */
@Configuration
public class HttpClientConfig {

    @Bean
    RestClient upstream(@Value("${upstream.url}") String url) {
        HttpClient client = HttpClient.newBuilder()
                // Evita a tentativa de upgrade para HTTP/2 e mantém o mesmo protocolo do Go.
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(10))
                .executor(Executors.newVirtualThreadPerTaskExecutor())
                .build();

        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(client);
        factory.setReadTimeout(Duration.ofSeconds(10));

        return RestClient.builder()
                .requestFactory(factory)
                .baseUrl(url)
                .build();
    }
}
