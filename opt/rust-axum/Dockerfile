FROM rust:1.99.1-slim-bookworm AS build
WORKDIR /src
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release --locked

# cc: o binário usa a glibc e a libgcc; o alocador é o mimalloc, ligado estaticamente.
FROM gcr.io/distroless/cc-debian12
COPY --from=build /src/target/release/rust-axum /app
# Devolve memória ao sistema sem atraso. Com os padrões, o mimalloc usou mais memória que a glibc.
ENV MIMALLOC_PURGE_DELAY=0 MIMALLOC_ARENA_EAGER_COMMIT=0
ENTRYPOINT ["/app"]
