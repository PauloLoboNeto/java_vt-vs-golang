// Carga de I/O com dois modos.
// MODE=vus (padrão): N usuários virtuais chamam /api/io em laço, sem pausa entre
// chamadas. Com 5s de latência fixa, o throughput ideal é VUS / 5.
// MODE=rate: VUS é a taxa em req/s, constante mesmo se o alvo ficar lento.
import http from 'k6/http';
import { sleep } from 'k6';
import { Trend, Counter } from 'k6/metrics';

const TARGET_URL = __ENV.TARGET_URL;
const VUS = parseInt(__ENV.VUS || '1000', 10);
const WARMUP = parseInt(__ENV.WARMUP || '30', 10);
const DURATION = parseInt(__ENV.DURATION || '180', 10);
const OUT = __ENV.OUT || '/results/k6.json';
const RATE_MODE = __ENV.MODE === 'rate';

const ioLatency = new Trend('io_latency', true);
const ioReqs = new Counter('io_reqs');
const ioErrors = new Counter('io_errors');
// Separa falhas de transporte (status 0: timeout, conexão) das respostas HTTP de erro.
const ioErrorsTransport = new Counter('io_errors_transport');

export const options = {
  discardResponseBodies: true,
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(50)', 'p(90)', 'p(95)', 'p(99)'],
  scenarios: {
    io: {
      ...(RATE_MODE
        ? {
            executor: 'constant-arrival-rate',
            rate: VUS,
            timeUnit: '1s',
            // Cada chamada dura 5s: VUS * 5 ficam em andamento. A folga absorve
            // alvos lentos; o que passar disso aparece em dropped_iterations.
            preAllocatedVUs: VUS * 6,
            maxVUs: VUS * 40,
          }
        : { executor: 'constant-vus', vus: VUS }),
      duration: `${WARMUP + DURATION}s`,
      // Precisa ser maior que o timeout da requisição. Senão, requisições
      // travadas somem da contagem sem virar erro.
      gracefulStop: '35s',
    },
  },
};

export function setup() {
  return { start: Date.now() };
}

export default function (data) {
  // Espalha os VUs nos 5s de latência para evitar ondas sincronizadas.
  if (!RATE_MODE && __ITER === 0) {
    sleep(Math.random() * 5);
  }

  const startedAt = Date.now();
  const res = http.get(TARGET_URL, { timeout: '30s' });

  // Conta só o que foi iniciado dentro da janela medida.
  const windowStart = data.start + WARMUP * 1000;
  const windowEnd = windowStart + DURATION * 1000;
  if (startedAt < windowStart || startedAt >= windowEnd) {
    return;
  }

  ioReqs.add(1);
  if (res.status === 200) {
    ioLatency.add(res.timings.duration);
  } else {
    ioErrors.add(1);
    if (res.status === 0) {
      ioErrorsTransport.add(1);
    }
  }
}

function values(data, name) {
  const metric = data.metrics[name];
  return metric ? metric.values : {};
}

function pick(v, key) {
  return v[key] === undefined ? null : v[key];
}

export function handleSummary(data) {
  const start = data.setup_data.start;
  const lat = values(data, 'io_latency');
  const blocked = values(data, 'http_req_blocked');
  const connecting = values(data, 'http_req_connecting');
  const requests = pick(values(data, 'io_reqs'), 'count') || 0;
  const errors = pick(values(data, 'io_errors'), 'count') || 0;

  const summary = {
    target_url: TARGET_URL,
    vus: VUS,
    warmup_s: WARMUP,
    duration_s: DURATION,
    window_start_ms: start + WARMUP * 1000,
    window_end_ms: start + (WARMUP + DURATION) * 1000,
    requests,
    errors,
    errors_transport: pick(values(data, 'io_errors_transport'), 'count') || 0,
    error_rate: requests > 0 ? errors / requests : 0,
    // Throughput real: só respostas 200. Erros rápidos não podem inflar o número.
    rps: (requests - errors) / DURATION,
    ideal_rps: RATE_MODE ? VUS : VUS / 5,
    mode: RATE_MODE ? 'rate' : 'vus',
    // Iterações que o k6 não conseguiu iniciar na taxa pedida. Zero no modo por VUs.
    dropped_iterations: pick(values(data, 'dropped_iterations'), 'count') || 0,
    latency_ms: {
      avg: pick(lat, 'avg'),
      min: pick(lat, 'min'),
      p50: pick(lat, 'p(50)'),
      p90: pick(lat, 'p(90)'),
      p95: pick(lat, 'p(95)'),
      p99: pick(lat, 'p(99)'),
      max: pick(lat, 'max'),
    },
    // http_req_duration não inclui conexão, por isso estes tempos são à parte.
    // Abrangem o teste inteiro, inclusive o warm-up, onde as conexões são abertas.
    http_req_blocked_ms: { p99: pick(blocked, 'p(99)'), max: pick(blocked, 'max') },
    http_req_connecting_ms: { p99: pick(connecting, 'p(99)'), max: pick(connecting, 'max') },
  };

  const text = `alvo=${TARGET_URL} vus=${VUS} reqs=${requests} erros=${errors} ` +
    `rps=${summary.rps.toFixed(1)}/${summary.ideal_rps} descartadas=${summary.dropped_iterations} ` +
    `p50=${summary.latency_ms.p50} p99=${summary.latency_ms.p99} max=${summary.latency_ms.max}\n`;

  return { [OUT]: JSON.stringify(summary, null, 2), stdout: text };
}
