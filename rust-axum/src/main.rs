// rust-axum recebe a requisição, chama a API externa e devolve a resposta.
// O handler não faz trabalho de CPU: o custo medido é o de esperar I/O.
use std::{env, sync::Arc, time::Duration, time::Instant};

use axum::{
    Router,
    extract::State,
    http::{StatusCode, header::CONTENT_TYPE},
    response::{IntoResponse, Response},
    routing::get,
    serve::ListenerExt,
};
use tokio::{
    net::TcpSocket,
    signal::unix::{SignalKind, signal},
};

#[derive(Clone)]
struct AppState {
    client: reqwest::Client,
    upstream: Arc<str>,
}

async fn io(State(state): State<AppState>) -> Response {
    let result = async {
        let resp = state.client.get(&*state.upstream).send().await?;
        let status = resp.status();
        Ok::<_, reqwest::Error>((status, resp.bytes().await?))
    }
    .await;

    match result {
        Ok((status, body)) => (status, [(CONTENT_TYPE, "application/json")], body).into_response(),
        Err(err) => (StatusCode::BAD_GATEWAY, err.to_string()).into_response(),
    }
}

#[tokio::main]
async fn main() -> std::io::Result<()> {
    let process_start = Instant::now();

    // Como PID 1, o processo ignoraria o SIGTERM e o docker esperaria 10s para encerrá-lo.
    let mut terminate = signal(SignalKind::terminate())?;
    tokio::spawn(async move {
        terminate.recv().await;
        std::process::exit(0);
    });

    let upstream =
        env::var("UPSTREAM_URL").unwrap_or_else(|_| "http://mock-api:8080/delay".to_string());

    // O reqwest não limita conexões por host: não precisa de ajuste como o MaxConnsPerHost do Go.
    let client = reqwest::Client::builder()
        .http1_only()
        .timeout(Duration::from_secs(10))
        .pool_idle_timeout(Duration::from_secs(60))
        .build()
        .map_err(std::io::Error::other)?;

    let app = Router::new()
        .route("/health", get(|| async { "ok" }))
        .route("/api/io", get(io))
        .with_state(AppState {
            client,
            upstream: upstream.into(),
        });

    // TcpListener::bind usa backlog de 1024, um gargalo artificial na subida dos VUs.
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
