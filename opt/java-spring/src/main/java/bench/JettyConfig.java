package bench;

import org.eclipse.jetty.server.HttpConnectionFactory;
import org.eclipse.jetty.util.thread.VirtualThreadPool;
import org.springframework.boot.jetty.servlet.JettyServletWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;

/** Remove dois limites do Jetty medidos com 10.000 conexões simultâneas. */
@Configuration
public class JettyConfig {

    // O VirtualThreadPool limita a 200 tarefas simultâneas por padrão: só 40 req/s com 5s de espera.
    private static final int MAX_CONCURRENT = 20000;

    @Bean
    @Order(Ordered.LOWEST_PRECEDENCE)
    WebServerFactoryCustomizer<JettyServletWebServerFactory> jettyLimits() {
        return factory -> {
            factory.setThreadPool(new VirtualThreadPool(MAX_CONCURRENT));
            // Cada conexão mantém o próprio cache de cabeçalhos, cerca de 100 KB por conexão.
            factory.addServerCustomizers(server -> {
                for (var connector : server.getConnectors()) {
                    var http = connector.getConnectionFactory(HttpConnectionFactory.class);
                    if (http != null) {
                        http.getHttpConfiguration().setHeaderCacheSize(0);
                    }
                }
            });
        };
    }
}
