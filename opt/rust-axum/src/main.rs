// Variante otimizada: usa hyper direto em vez de reqwest, mimalloc em vez do
// alocador da glibc e compilação com LTO. O contrato é o mesmo do alvo padrão.
use std::{env, time::Duration, time::Instant};

use axum::{
    Router,
    body::{Body, Bytes},
    extract::State,
    http::{StatusCode, Uri, header::CONTENT_TYPE},
    response::{IntoResponse, Response},
    routing::get,
    serve::ListenerExt,
};
use http_body_util::{BodyExt, Empty};
use hyper_util::{
    client::legacy::{Client, connect::HttpConnector},
    rt::{TokioExecutor, TokioTimer},
};
use tokio::{
    net::TcpSocket,
    signal::unix::{SignalKind, signal},
    time::timeout,
};

#[global_allocator]
static GLOBAL: mimalloc::MiMalloc = mimalloc::MiMalloc;

// Leitura com buffer fixo de 2 KiB, em vez do adaptativo que começa em 8 KiB.
const READ_BUFFER_SIZE: usize = 2048;

#[derive(Clone)]
struct AppState {
    client: Client<HttpConnector, Empty<Bytes>>,
    upstream: Uri,
}

async fn call(state: &AppState) -> Result<(StatusCode, Bytes), String> {
    let exchange = async {
        let resp = state
            .client
            .get(state.upstream.clone())
            .await
            .map_err(|e| e.to_string())?;
        let status = resp.status();
        let body = resp.into_body().collect().await.map_err(|e| e.to_string())?;
        Ok((status, body.to_bytes()))
    };
    timeout(Duration::from_secs(10), exchange)
        .await
        .map_err(|e| e.to_string())?
}

async fn io(State(state): State<AppState>) -> Response {
    match call(&state).await {
        Ok((status, body)) => {
            (status, [(CONTENT_TYPE, "application/json")], Body::from(body)).into_response()
        }
        Err(err) => (StatusCode::BAD_GATEWAY, err).into_response(),
    }
}

#[tokio::main]
async fn main() -> std::io::Result<()> {
    let process_start = Instant::now();

    let mut terminate = signal(SignalKind::terminate())?;
    tokio::spawn(async move {
        terminate.recv().await;
        std::process::exit(0);
    });

    let upstream = env::var("UPSTREAM_URL")
        .unwrap_or_else(|_| "http://mock-api:8080/delay".to_string())
        .parse::<Uri>()
        .map_err(std::io::Error::other)?;

    let mut connector = HttpConnector::new();
    connector.set_nodelay(true);
    let client = Client::builder(TokioExecutor::new())
        .pool_timer(TokioTimer::new())
        .pool_idle_timeout(Duration::from_secs(60))
        .http1_read_buf_exact_size(READ_BUFFER_SIZE)
        .build(connector);

    let app = Router::new()
        .route("/health", get(|| async { "ok" }))
        .route("/api/io", get(io))
        .with_state(AppState { client, upstream });

    let socket = TcpSocket::new_v4()?;
    socket.set_reuseaddr(true)?;
    socket.bind(([0, 0, 0, 0], 8080).into())?;
    let listener = socket.listen(65535)?.tap_io(|tcp| {
        let _ = tcp.set_nodelay(true);
    });

    // O formato abaixo é lido por scripts/startup.py.
    eprintln!("started in {:.3} seconds", process_start.elapsed().as_secs_f64());
    axum::serve(listener, app).await
}
