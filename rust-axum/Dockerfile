FROM rust:1.99.1-slim-bookworm AS build
WORKDIR /src
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release --locked

# cc: o binário usa a glibc e a libgcc, com o alocador padrão.
FROM gcr.io/distroless/cc-debian12
COPY --from=build /src/target/release/rust-axum /app
ENTRYPOINT ["/app"]
