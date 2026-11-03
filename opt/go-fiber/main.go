// go-fiber recebe a requisição, chama a API externa e devolve a resposta.
// O handler não faz trabalho de CPU: o custo medido é o de esperar I/O.
package main

import (
	"log"
	"os"
	"time"

	"github.com/gofiber/fiber/v3"
	"github.com/valyala/fasthttp"
)

// processStart é inicializada antes de main, o mais perto possível do início
// do processo, e serve de base para o tempo de startup autodeclarado.
var processStart = time.Now()

// bufferSize também limita o tamanho dos cabeçalhos aceitos a 2 KiB.
const bufferSize = 2048

func main() {
	upstream := os.Getenv("UPSTREAM_URL")
	if upstream == "" {
		upstream = "http://mock-api:8080/delay"
	}

	client := &fasthttp.Client{
		// O padrão de 512 conexões por host criaria um gargalo artificial.
		MaxConnsPerHost:          20000,
		ReadTimeout:              10 * time.Second,
		WriteTimeout:             10 * time.Second,
		MaxIdleConnDuration:      60 * time.Second,
		NoDefaultUserAgentHeader: true,
		// Otimização: o padrão de 4 KiB por conexão pesa com milhares de chamadas paradas.
		ReadBufferSize:  bufferSize,
		WriteBufferSize: bufferSize,
	}

	app := fiber.New(fiber.Config{
		ReadBufferSize:  bufferSize,
		WriteBufferSize: bufferSize,
	})

	app.Hooks().OnListen(func(fiber.ListenData) error {
		// O formato abaixo é lido por scripts/startup.py.
		log.Printf("started in %.3f seconds", time.Since(processStart).Seconds())
		return nil
	})

	app.Get("/health", func(c fiber.Ctx) error {
		return c.SendString("ok")
	})

	app.Get("/api/io", func(c fiber.Ctx) error {
		req := fasthttp.AcquireRequest()
		resp := fasthttp.AcquireResponse()
		defer fasthttp.ReleaseRequest(req)
		defer fasthttp.ReleaseResponse(resp)

		req.SetRequestURI(upstream)
		req.Header.SetMethod(fasthttp.MethodGet)

		if err := client.Do(req, resp); err != nil {
			return c.Status(fiber.StatusBadGateway).SendString(err.Error())
		}

		c.Status(resp.StatusCode())
		c.Set(fiber.HeaderContentType, fiber.MIMEApplicationJSON)
		// SetBody copia os bytes. c.Send poderia reter o buffer de resp, que
		// volta ao pool no defer e seria reaproveitado por outra requisição.
		c.Response().SetBody(resp.Body())
		return nil
	})

	log.Fatal(app.Listen(":8080", fiber.ListenConfig{DisableStartupMessage: true}))
}
