FROM golang:1.27.3 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY main.go ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /app .

FROM gcr.io/distroless/static-debian12
COPY --from=build /app /app
# GOMEMLIMIT: o GC fica mais agressivo perto do limite de 1 GB, em vez de deixar o kernel matar o processo.
ENV GOMEMLIMIT=900MiB
ENTRYPOINT ["/app"]
