// mock-api simula a API externa: cada chamada fica parada por DELAY e devolve
// um JSON fixo. Usa só a biblioteca padrão para ser fácil de auditar.
package main

import (
	"log"
	"net/http"
	"os"
	"time"
)

var body = []byte(`{"status":"ok","source":"mock-api"}`)

func main() {
	delay := 5 * time.Second
	if v := os.Getenv("DELAY"); v != "" {
		d, err := time.ParseDuration(v)
		if err != nil {
			log.Fatalf("DELAY inválido %q: %v", v, err)
		}
		delay = d
	}

	mux := http.NewServeMux()
	mux.HandleFunc("GET /delay", func(w http.ResponseWriter, _ *http.Request) {
		time.Sleep(delay)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(body)
	})
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte("ok"))
	})

	srv := &http.Server{
		Addr:              ":8080",
		Handler:           mux,
		ReadHeaderTimeout: 10 * time.Second,
		IdleTimeout:       120 * time.Second,
	}
	log.Printf("mock-api ouvindo em :8080 com atraso de %s", delay)
	log.Fatal(srv.ListenAndServe())
}
