package bench;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/** Mesmo contrato do alvo Go: /health e /api/io, sem trabalho de CPU no handler. */
@RestController
public class IoController {

    private final RestClient upstream;

    IoController(RestClient upstream) {
        this.upstream = upstream;
    }

    @GetMapping("/health")
    String health() {
        return "ok";
    }

    @GetMapping("/api/io")
    ResponseEntity<byte[]> io() {
        ResponseEntity<byte[]> resp = upstream.get().retrieve().toEntity(byte[].class);
        return ResponseEntity.status(resp.getStatusCode())
                .contentType(MediaType.APPLICATION_JSON)
                .body(resp.getBody());
    }

    /** Falha ao chamar a API externa vira 502, como no alvo Go. */
    @ExceptionHandler(RestClientException.class)
    ResponseEntity<String> upstreamError(RestClientException e) {
        return ResponseEntity.status(HttpStatus.BAD_GATEWAY).body(String.valueOf(e.getMessage()));
    }
}
