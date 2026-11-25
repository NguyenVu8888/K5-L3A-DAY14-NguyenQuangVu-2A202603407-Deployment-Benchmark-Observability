# Benchmark & Observability Report — Day 14

> **Họ tên:** Nguyen Quang Vu (MSSV: 2A202603407 · Lớp: K5-L3A)  
> **Ngày chạy:** 2026-11-26  
> **Môi trường:** Windows 11, Python 3.12.10, Docker Desktop 29.9.3 (Linux containers), Docker Compose v5.7.1  

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | `< 500 ms` | Mock LLM có latency nền ~120–180 ms + retrieval ~20 ms; ngưỡng 500 ms đảm bảo 95% người dùng nhận phản hồi dưới nửa giây khi không rơi vào tail latency |
| Error rate `/ask` | `< 2.0 %` | Mock LLM giả lập ~1% lỗi upstream (`MOCK_ERROR_RATE=0.01`); đặt SLO 2% cho phép dung sai lỗi transient nhỏ nhưng vẫn phát hiện ngay khi lỗi tăng bất thường |
| Accuracy trên golden dataset | `≥ 85 %` (CI gate) / `100 %` (sau khi sửa KB) | Golden dataset gồm 23 câu hỏi cốt lõi; ngưỡng CI 85% chặn merge bản code/prompt suy giảm chất lượng, và mục tiêu cuối là đạt 23/23 không regression |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2 — 300 requests mỗi mức)

Nguồn dữ liệu: `reports/load_v2_c1.json`, `reports/load_v2_c10.json`, `reports/load_v2_c50.json`, `reports/load_v2_c100.json`.

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 3.4 | 214.1 | 1018.4 | 1748.5 | 1.00% | FAIL (p95 > 500 ms) |
| 10 | 38.01 | 199.5 | 242.2 | 1716.9 | 1.00% | PASS |
| 50 | 42.47 | 336.8 | 4345.2 | 5248.7 | 0.33% | FAIL (p95 > 500 ms) |
| 100 | 35.4 | 1381.9 | 5835.8 | 6729.0 | 1.00% | FAIL (p95 > 500 ms) |

**Nhận xét:** RPS **không** tăng tuyến tính theo concurrency. Từ `c=1` (`3.4 req/s`) lên `c=10` (`38.01 req/s`), RPS tăng mạnh nhờ xử lý bất đồng bộ (`async/await`). Tuy nhiên từ `c=50` (`42.47 req/s`) sang `c=100` (`35.4 req/s`), hệ thống chạm trần xử lý của 1 process `uvicorn` + socket localhost trên Windows, khiến hàng đợi request phình to và p50/p95 tăng vọt từ `242.2 ms` lên `5835.8 ms` (*Little's Law*). Ở `c=1`, mẫu chỉ có 1 luồng tuần tự và ngẫu nhiên gặp số request slow (`MOCK_SLOW_RATE=0.03`) vừa đủ đẩy p95 lên `1018.4 ms`.

### 2.2 Tail latency (`--requests 300 --concurrency 20`)

Nguồn dữ liệu: `reports/load_v2_slow_0.json`, `reports/load_v2_slow_0.03.json`, `reports/load_v2_slow_0.1.json`.

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 208.6 | 264.1 | 286.3 |
| 0.03 (mặc định) | 256.1 | 266.2 | 1708.5 |
| 0.1 | 400.9 | 1719.7 | 1893.2 |

**Nhận xét:** **p99** (và **p95** khi tỉ lệ chậm lên 10%) nhạy nhất với các request chậm bất thường: từ `MOCK_SLOW_RATE=0` sang `0.03`, `avg` chỉ tăng nhẹ `+47.5 ms` (`208.6 → 256.1 ms`) nhưng `p99` nhảy vọt gần **6 lần** (`286.3 → 1708.5 ms`). Nếu đặt SLO theo `average`, phần lớn request nhanh sẽ "che lấp" trải nghiệm tệ của nhóm người dùng gặp tail latency.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Nguồn dữ liệu: `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json`.

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.6 | 108.8 | 113.7 |
| Tổng cost (USD) | $0.000411 | $0.000758 | $0.000790 |
| Cost / câu đúng (USD) | $0.00041115 | $0.00003607 | $0.00003436 |
| Quality gate | FAIL | PASS (gate ≥ 80%) | PASS (gate 100%, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách sửa (`utils/mock_llm.py`):**

| ID | Keyword bị thiếu | Đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry `(["jwt"], ...)` vào `KNOWLEDGE_BASE` giải thích JWT chứa chữ ký số và thời điểm hết hạn, khác với API key cố định |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry `(["hpa", "kubernetes", "autoscal"], ...)` vào `KNOWLEDGE_BASE` giải thích Kubernetes HPA scale pod dựa trên CPU, memory hoặc custom metrics |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**  
Agent v2 thêm bước retrieval (RAG) nên prompt dài hơn khiến `avg_tokens` gần gấp đôi (`57.6 → 113.7`) và tổng cost gần gấp đôi (`$0.000411 → $0.000790`), nhưng đổi lại độ chính xác tăng từ `4.3%` lên `100.0%`. Nhờ vậy chỉ số **`cost / câu đúng`** của v2 thực tế **rẻ hơn ~12 lần** so với v1 (`$0.00003436` so với `$0.00041115`). Trong CI/CD (`.github/workflows/eval.yml`), `run_eval.py --min-accuracy 0.85` trả về exit code `1` nếu accuracy dưới ngưỡng hoặc có regression, giúp GitHub Actions tự động chặn PR trước khi merge.

---

## 4. Observability stack (production)

### 4.1 Screenshot & Trả lời Exercise 7.4

- [x] Dashboard Grafana khi đang có tải: [grafana-dashboard.png](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger: [jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger: [jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với cả **4/4 alerts** đang **FIRING**: [prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)

**Trả lời câu hỏi Exercise 7.4 (số liệu truy vấn thực tế từ Prometheus/Nginx):**
1. **p95 và avg:** `p95 = 702.65 ms`, `avg = 286.38 ms`. Khoảng cách hơn 2.4 lần giữa `p95` và `avg` phản ánh tail latency do ~3% request rơi vào nhánh `MOCK_SLOW_MS=1500 ms` và hàng đợi khi chịu tải 100 users.
2. **Requests/s theo instance:** Khi chạy 2 instance, Prometheus đo được `17.26 req/s` (`172.18.0.7:8000`) và `16.96 req/s` (`172.18.0.8:8000`) — Nginx chia tải gần như đều tuyệt đối (~50/50) theo round-robin.
3. **Vì sao `input tokens/s` (`2624.6/s`) lớn hơn `output tokens/s` (`1370.4/s`)?** Vì mỗi prompt gửi lên LLM bao gồm cả `SYSTEM_PROMPT` + context tài liệu retrieval (`KNOWLEDGE_BASE`) + câu hỏi người dùng, trong khi câu trả lời ngắn gọn hơn nhiều.
4. **`curl -i http://localhost:8080/metrics` trả về gì và vì sao?** Trả về **`HTTP/1.1 404 Not Found`** từ Nginx (`location = /metrics { return 404; }` trong `nginx.conf`) nhằm bảo mật, không public endpoint metrics nội bộ ra ngoài internet; chỉ Prometheus trong `obs_net` mới scrape trực tiếp `agent:8000/metrics`.

### 4.2 Thí nghiệm "phá hệ thống"

Thực hiện đồng thời cấu hình lỗi (`MOCK_ERROR_RATE=0.2`, `MOCK_SLOW_RATE=0.3`, `LLM_MODEL=mock-llm-large`) + Locust load 30 users + `docker pause k5-day14-observability-agent-2` và theo dõi `/api/v1/alerts`:

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`for: 1m`) | **82s** | *Error rate* (Golden Signals) & *Requests/s theo status code* (`503` tăng vọt) |
| B | `MOCK_SLOW_RATE=0.3` + `mock-llm-large` | `AgentHighLatencyP95` (`for: 2m`) | **142s** | *Latency p95* & *Latency /ask — p50/p95/p99* |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (`for: 2m`) | **~152s** (`pending` ở t=142s, chuyển `FIRING` ngay lúc chụp ảnh Alerts) | *Cost burn rate (USD/giờ)* & *LLM cost (1h)* |
| D | `docker pause k5-day14-observability-agent-2` | `AgentInstanceDown` (`for: 30s`) | **42s** | *Instances up* (giảm từ 2 xuống 1) |
| E | `AGENT_VERSION=v1` | Không có alert nào firing | Không firing | *Retrieval hit ratio (agent v2)* giảm về 0, *Tokens/s* giảm |

**Thí nghiệm E không làm alert nào firing. Phát hiện loại sự cố này trong production bằng cách nào?**  
Lỗi suy giảm chất lượng trả lời (regression do đổi model, prompt, hoặc mất retrieval) không làm tăng HTTP 5xx hay latency nên metric hạ tầng vẫn xanh. Để phát hiện trong production cần:
1. Chạy **Eval & Quality Gate** (`run_eval.py` với golden dataset) tự động trong CI/CD trước khi deploy.
2. Áp dụng **online evaluation / canary evaluation** (lấy mẫu traffic thật chấm bằng LLM-as-judge), theo dõi tỷ lệ retrieval hit ratio và thu thập feedback người dùng (thumbs up/down).

### 4.3 Debug bằng trace

Trace chậm nhất tìm được trong Jaeger (`trace_id` khớp log JSON):

- `trace_id`: `c1de1ff382995dcfe951cf2a18347233`
- Tổng thời gian (`POST /ask`): `1729.82 ms`
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (`1699.73 ms`, **98.3%** tổng thời gian — trong khi `agent.retrieve_context` chỉ mất `19.57 ms`, `1.1%`)
- Dòng log JSON tương ứng (`docker compose -p k5-day14-observability logs agent | grep c1de1ff382995dcfe951cf2a18347233`):

```json
{"ts": "2026-11-25T18:18:13.728549+00:00", "level": "INFO", "service": "observable-agent", "instance": "04af7b26f171", "event": "llm_call", "trace_id": "c1de1ff382995dcfe951cf2a18347233", "span_id": "a5ffa4a33577d167", "request_id": "0f2688087a0e", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1698.8}
```

*(Trace lỗi tham chiếu: `351cc165a2b3b4e0dd22fc0a93a72de5`, sự kiện `llm_error` 503 từ upstream LLM mock.)*

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Nguồn dữ liệu: `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv` (dòng `Aggregated` và `POST /ask`).

| Số instance | RPS (Aggregated / `/ask`) | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 63.46 (57.60 `/ask`) | 210 | 690 (`720` `/ask`) | 1700 | 70 / 7364 (0.95%) |
| 3 | 61.49 (56.13 `/ask`) | 220 | 830 (`880` `/ask`) | 1700 | 62 / 7269 (0.85%) |

**Giải thích kết quả:**  
Khi tăng từ 1 lên 3 instance trong bài test 100 Locust users (`wait_time` ~0.5–1.5s), RPS giữ ở mức ~61–63 req/s và `p95` không giảm thêm (`690 ms` vs `830 ms`). Có hai nguyên nhân chính:
1. **Nút thắt nằm ở tầng LLM async I/O (`await asyncio.sleep(...)` ~150–200 ms + 3% tail latency 1500 ms) và mức tải đầu vào của Locust:** 1 process FastAPI/uvicorn bất đồng bộ đã dư sức gánh 100 user ở ~63 RPS mà chưa nghẽn CPU; do đó tăng thêm instance không làm mỗi lệnh gọi LLM chạy nhanh hơn.
2. **Tài nguyên máy host khi chạy cả stack Docker trên laptop:** Trên cùng một máy Windows chạy Docker Desktop, 3 container agent + Nginx + Prometheus + Grafana + Jaeger + Locust cùng chia sẻ CPU/network bridge khiến overhead điều phối nhích nhẹ ở tail/p95 (`690 → 830 ms`). Scale ngang thực sự phát huy tác dụng khi tải tăng cao hơn nữa (nghẽn CPU/event loop trên 1 instance) hoặc khi phân tán ra nhiều node vật lý khác nhau.

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. **Percentile quan trọng hơn trung bình:** Latency trung bình che giấu tail latency; phải dùng p95/p99 và đặt SLO theo percentile kết hợp error budget.
  2. **Tách biệt đánh giá hiệu năng và chất lượng:** Metrics hạ tầng xanh không đồng nghĩa agent trả lời đúng — luôn cần eval trên golden dataset và quality gate trong CI/CD (đặc biệt nhìn vào `cost / câu đúng` thay vì chỉ `cost / câu`).
  3. **3 trụ cột Metrics – Traces – Logs liên kết chặt chẽ:** Prometheus/Grafana phát hiện bất thường nhanh, Jaeger chỉ ra đúng span gây chậm (`chat mock-llm-small` 98.3%), và `trace_id` giúp truy vết ngay dòng log JSON chi tiết.
- **Nếu đưa agent này lên production thật, sẽ thêm metric / alert nào nữa?**
  1. Theo dõi **TTFT (Time To First Token)** và **TPOT (Time Per Output Token)** cho streaming response.
  2. Thêm metric/alert về **rate limit hit rate (429)**, **budget rejection (402)**, và **Redis latency/connection pool saturation** để phát hiện sớm lạm dụng hoặc nghẽn state store.
  3. Thêm **online quality/hallucination score** hoặc **retrieval empty-hit rate** để cảnh báo khi chất lượng RAG tụt giảm trên traffic thật.
