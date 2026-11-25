# Day 14 Lab — Mission Answers

> **Họ và tên:** Nguyen Quang Vu  
> **MSSV:** 2A202603407  
> **Lớp:** K5-L3A  

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns phát hiện trong `01-localhost-vs-production/develop/app.py`

1. **Hardcode secrets ngay trong mã nguồn (dòng 17–18):**
   - `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`.
   - **Nguy cơ:** Khi push lên Git/GitHub, key và mật khẩu bị lộ vĩnh viễn trong lịch sử commit; kẻ xấu có thể lấy key gọi API gây mất tiền hoặc truy cập trái phép DB.
   - **Cách bản `production` sửa:** Tập trung cấu hình trong `production/config.py` (dòng 15–50), đọc toàn bộ từ biến môi trường bằng `os.getenv(...)`, validate fail-fast khi `ENVIRONMENT=production` (dòng 42–43) và cung cấp `.env.example` (không commit `.env`).
2. **Hardcode cấu hình ứng dụng, không có config management (dòng 21–22):**
   - `DEBUG = True`, `MAX_TOKENS = 500` viết cứng trong code. Không thể thay đổi hành vi giữa các môi trường `dev` / `staging` / `production` mà không sửa code và rebuild.
   - **Cách bản `production` sửa:** Đọc `DEBUG`, `MAX_TOKENS`, `ENVIRONMENT`, `LLM_MODEL` từ biến môi trường trong `config.py`.
3. **Dùng `print()` thay cho structured logging và in trực tiếp secret ra log (dòng 33–38):**
   - `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` vừa làm lộ secret trong log, vừa không có timestamp, log level hay cấu trúc JSON nên các hệ thống gom log (Loki, Datadog, CloudWatch) không thể parse/filter.
   - **Cách bản `production` sửa:** Dùng module `logging` xuất log định dạng JSON (`app.py`, dòng 28–32 và 111–122), chỉ log metadata (`event`, `question_length`, `client_ip`) và tuyệt đối không log secret.
4. **Không có Health Check / Readiness Check endpoint:**
   - Khi app treo, crash hoặc chưa khởi tạo xong kết nối DB/Redis, nền tảng cloud / orchestrator / load balancer không biết để tự restart hoặc ngừng đẩy traffic vào.
   - **Cách bản `production` sửa:** Bổ sung `GET /health` (liveness probe, dòng 135–149) và `GET /ready` (readiness probe trả `503` khi `is_ready=False`, dòng 152–161).
5. **Bind `host="localhost"`, hardcode `port=8000` và bật `reload=True` (dòng 49–54):**
   - `host="localhost"` chỉ nhận kết nối từ chính máy đó → chạy trong Docker container hoặc cloud sẽ không truy cập được từ bên ngoài.
   - `port=8000` cố định → lỗi trên Railway/Render vốn tự động inject biến `PORT`.
   - `reload=True` tốn tài nguyên theo dõi file và có thể làm restart process bất ngờ trên production.
   - **Cách bản `production` sửa:** Bind `settings.host` (mặc định `0.0.0.0`), `port=settings.port` (từ env `PORT`), `reload=settings.debug` (`false` mặc định) ở dòng 194–199.
6. **Không có Graceful Shutdown & Lifecycle Management:**
   - Khi container nhận tín hiệu `SIGTERM` (deploy bản mới hoặc scale down), process tắt đột ngột làm ngắt ngang các request đang xử lý (in-flight requests).
   - **Cách bản `production` sửa:** Dùng FastAPI `lifespan` (dòng 39–67) để set `is_ready = False` khi tắt và đăng ký handler `signal.SIGTERM` (dòng 180–189) cho phép hoàn tất request đang chạy.
7. **Nhận input qua query string không kiểm soát và không cấu hình CORS (dòng 30–31):**
   - `POST /ask?question=...` dễ lộ câu hỏi trong access log/URL và không có validation chuẩn.
   - **Cách bản `production` sửa:** Nhận JSON body, validate trả lỗi `422` rõ ràng nếu thiếu `question` (dòng 102–108), cấu hình `CORSMiddleware` theo `ALLOWED_ORIGINS` (dòng 77–82).

### Exercise 1.2: Kết quả chạy thử nghiệm

**Bản `develop/app.py`** (`POST http://localhost:8000/ask?question=Hello`):
```text
HTTP 200: {"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

**Bản `production/app.py`**:
```text
GET  /health -> HTTP 200: {"status":"ok","uptime_seconds":0.4,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T10:01:18.770848+00:00"}
GET  /ready  -> HTTP 200: {"ready":true}
POST /ask    -> HTTP 200: {"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","model":"gpt-4o-mini"}
```

### Exercise 1.3: Bảng so sánh Develop vs Production

| Feature | Develop (`develop/app.py`) | Production (`production/app.py`) | Tại sao quan trọng? |
|---|---|---|---|
| **Config & Secrets** | Hardcode `OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG=True` trong code | Đọc từ biến môi trường qua `config.py` (`os.getenv`), fail-fast khi thiếu secret ở production | Tránh lộ secret lên Git; dùng chung 1 artifact/image cho dev, staging, production mà chỉ cần đổi env |
| **Health & Readiness Check** | Không có | Có `GET /health` (liveness) và `GET /ready` (readiness trả `503` nếu chưa sẵn sàng) | Cloud/Docker/K8s dùng `/health` để tự restart container bị treo; Load Balancer dùng `/ready` để không đẩy traffic vào instance chưa sẵn sàng |
| **Logging** | `print()` văn bản tự do, in cả `OPENAI_API_KEY` | Structured JSON logging qua `logging`, không log secret | Log JSON giúp hệ thống observability (Loki, Datadog, ELK) index, tìm kiếm và cảnh báo tự động; bảo vệ thông tin nhạy cảm |
| **Shutdown** | Tắt đột ngột | FastAPI `lifespan` + xử lý `SIGTERM` (graceful shutdown) | Đảm bảo request đang xử lý được hoàn thành trọn vẹn trước khi tắt container, tránh lỗi 502/504 cho người dùng khi deploy |
| **Network & Server** | `host="localhost"`, `port=8000`, `reload=True` | `host="0.0.0.0"`, `port` từ env `PORT`, `reload=settings.debug` (`false`) | `0.0.0.0` cho phép nhận traffic từ ngoài container; `PORT` động tương thích Railway/Render; tắt reload để ổn định hiệu năng |
| **Security & Input** | Không CORS, nhận `question` qua query param | `CORSMiddleware` cấu hình được, nhận JSON body và validate trả `422` | Kiểm soát nguồn gọi API từ trình duyệt, tránh lộ dữ liệu nhạy cảm trên URL và trả lỗi chuẩn cho client |

---

## Part 2: Docker

### Exercise 2.1: Phân tích `02-docker/develop/Dockerfile`

1. **Base image:** `python:3.11` (bản đầy đủ ~1 GB, chứa sẵn build tools và nhiều thư viện hệ thống).
2. **Working directory:** `/app` (`WORKDIR /app`).
3. **Tại sao `COPY 02-docker/develop/requirements.txt .` đứng trước `COPY 02-docker/develop/app.py .`?**
   - Để tận dụng **Docker layer cache**. Khi chỉ sửa mã nguồn `app.py` mà không đổi `requirements.txt`, Docker tái sử dụng lại layer `RUN pip install ...` đã cache thay vì tải và cài lại toàn bộ thư viện.
4. **`CMD` khác `ENTRYPOINT` thế nào?**
   - `CMD` định nghĩa lệnh và tham số mặc định khi container chạy, **dễ bị ghi đè** nếu truyền command lúc `docker run <image> <cmd>`.
   - `ENTRYPOINT` cố định file thực thi chính của container; các đối số truyền thêm vào `docker run` sẽ được nối vào sau `ENTRYPOINT` thay vì thay thế hoàn toàn.

### Exercise 2.2: Build và chạy `my-agent:develop`

- Lệnh build từ gốc repo: `docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .`
- Kết quả gọi `POST http://127.0.0.1:8000/ask?question=What+is+Docker`:
```json
HTTP 200: {"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

### Exercise 2.3: Multi-stage build (`02-docker/production/Dockerfile`) & so sánh dung lượng

- **Stage 1 (`builder`):** Dùng `python:3.11-slim`, cài `gcc` và `libpq-dev`, chạy `pip install --no-cache-dir --user -r requirements.txt` vào `/root/.local`. Image trung gian này không dùng để chạy production.
- **Stage 2 (`runtime`):** Tạo mới từ `python:3.11-slim`, tạo non-root user `appuser`, chỉ `COPY --from=builder /root/.local /home/appuser/.local` cùng `main.py` và `utils/mock_llm.py`, bổ sung `HEALTHCHECK` — loại bỏ hoàn toàn compiler/build tools.

**Kết quả đo thực tế bằng `docker images` và `docker image inspect`:**
- **Develop (`my-agent:develop`):** `1.67 GB` (`1,667,787,968` bytes ≈ `1,590.5 MiB` / `1,667.8 MB`)
- **Production (`my-agent:advanced`):** `240 MB` (`239,815,530` bytes ≈ `228.7 MiB` / `239.8 MB`)
- **Chênh lệch:** Giảm **85.62%** dung lượng (`-1,427,972,438` bytes).

### Exercise 2.4: Docker Compose Stack (`02-docker/production/docker-compose.yml`)

**Sơ đồ kiến trúc stack (4 services giao tiếp qua bridge network `internal`):**
```text
Client ──(:80)──▶ [ Nginx (reverse proxy / LB) ]
                         │
                         ▼ (:8000 internal)
                  [ Agent (FastAPI) ]
                     ├──(:6379)──▶ [ Redis (cache / rate limit) ]
                     └──(:6333)──▶ [ Qdrant (vector DB) ]
```

**Kết quả test qua Nginx:**
```text
GET  /health -> HTTP 200: {"status":"ok","uptime_seconds":1.2,"version":"2.0.0","timestamp":"2026-11-25T17:45:16.397687"}
POST /ask    -> HTTP 200: {"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

---

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deploy Agent Part 6 (`06-lab-complete/`)
- **Public URL:** `<YOUR_PUBLIC_URL>` *(chờ Vũ đăng nhập Railway/Render và chạy `railway up` trong `06-lab-complete/`)*
- **Nền tảng:** Railway (`06-lab-complete/railway.toml`) + Redis managed service
- **Screenshots:** `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png`

### So sánh `railway.toml` vs `render.yaml`

| Tiêu chí | `railway.toml` | `render.yaml` |
|---|---|---|
| **Định dạng & vai trò** | TOML ngắn gọn, cấu hình build & deploy cho **1 service** hiện tại | YAML Blueprint (Infrastructure as Code), khai báo được **cả stack nhiều services/databases** trong 1 file |
| **Cách chỉ định build** | `[build]` với `builder = "DOCKERFILE"` | Trong từng service đặt `runtime: docker` |
| **Health check** | `healthcheckPath = "/health"` trong `[deploy]` | `healthCheckPath: /health` trong spec của service |
| **Biến môi trường & secrets** | Thiết lập qua CLI (`railway variables set ...`) hoặc dashboard, không cần ghi vào `railway.toml` | Khai báo trực tiếp danh sách `envVars` trong `render.yaml`; secret dùng `generateValue: true` hoặc `sync: false` để tránh hardcode |
| **Multi-service (Redis)** | Tạo Redis plugin/service riêng trên dashboard Railway và tham chiếu biến `${{Redis.REDIS_URL}}` | Có thể khai báo luôn service `type: keyvalue` (hoặc Redis) trong cùng Blueprint và link bằng `fromService` |

### Exercise 3.3: Mô tả CI/CD Pipeline GCP Cloud Run (`03-cloud-deployment/production-cloud-run/`)

Dựa trên `cloudbuild.yaml` và `service.yaml`, pipeline CI/CD của Cloud Run gồm 4 bước tuần tự khi có commit lên nhánh `main`:
1. **Test (`test`):** Dùng container `python:3.11-slim` cài `requirements.txt` + `pytest` và chạy `pytest tests/`; nếu fail thì dừng pipeline ngay.
2. **Build (`build`):** Dùng `cloud-builders/docker` build Docker image với layer cache (`--cache-from ...:latest`) và gắn 2 tag (`$COMMIT_SHA` và `latest`).
3. **Push (`push`):** Đẩy các tag image vừa build lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **Deploy (`deploy`):** Dùng `gcloud run deploy` triển khai image `$COMMIT_SHA` lên Cloud Run (`asia-southeast1`), cấu hình `--min-instances=1` (tránh cold start), `--max-instances=10`, giới hạn CPU/RAM (`1` vCPU, `512Mi`), inject secret từ Google Secret Manager (`--set-secrets`) và kết hợp `service.yaml` (Knative Service IaC với `containerConcurrency: 80`, `livenessProbe` `/health` và `startupProbe` `/ready`).

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/app.py`)

- **Kiểm tra ở đâu:** Dependency `verify_api_key` dùng `APIKeyHeader(name="X-API-Key", auto_error=False)` gắn vào endpoint `POST /ask` (`Depends(verify_api_key)`).
- **Khi thiếu hoặc sai key:** Thiếu key trả về `401 Unauthorized`; sai key trả về `403 Forbidden` (trong bản production Part 6 chuẩn hoá đều về `401`).
- **Cách rotate key:** Đọc `AGENT_API_KEY` từ biến môi trường; có thể hỗ trợ danh sách nhiều key hợp lệ (`key_cũ,key_mới`) trong giai đoạn chuyển tiếp rồi thu hồi key cũ mà không cần downtime.

**Kết quả test thực tế (`AGENT_API_KEY=secret-key-123`):**

1. **Không có key (`401 Unauthorized`):**
```http
HTTP/1.1 401 Unauthorized
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

2. **Có key (`X-API-Key: secret-key-123` → `200 OK`):**
```http
HTTP/1.1 200 OK
content-type: application/json

{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production/`)

- **JWT Flow (`auth.py`):** Client gửi `POST /auth/token` với `{"username": "student", "password": "demo123"}` → server xác thực và ký JWT (`HS256`, chứa `sub`, `role`, `iat`, `exp=60 phút`). Khi gọi `POST /ask`, client gửi `Authorization: Bearer <REDACTED_JWT>` → `verify_token` kiểm tra chữ ký và hạn dùng không cần tra DB.
- **Rate Limiter (`rate_limiter.py`):**
  - **Thuật toán:** Sliding Window Counter dùng `deque` lưu timestamp của từng user.
  - **Giới hạn:** Role `user` (`student`) tối đa **10 requests/60 giây**; role `admin` (`teacher`) tối đa **100 requests/60 giây** (tách 2 instance `rate_limiter_user` và `rate_limiter_admin`).

**Kết quả test thực tế (Request 1 → `200`, Request 11 → `429`):**
```http
# Request 1 (Authorization: Bearer <REDACTED_JWT>)
HTTP/1.1 200 OK
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"what is docker?","answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}
```
Sau các request 2–10 trả `200 OK`, đến **Request 11** vượt ngưỡng 10 req/phút:
```http
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795627913
retry-after: 59
content-type: application/json

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Exercise 4.4: Cost Guard với Redis

- **Cách thiết kế:**
  - Dùng khóa Redis theo user và chu kỳ ngày/tháng: `budget:{user_id}:{YYYY-MM}` (hoặc `cost:daily:{YYYY-MM-DD}`).
  - **Trước khi gọi LLM (`check_budget`):** Đọc chi phí hiện tại bằng `r.get(key)`. Nếu `current >= budget_limit` → chặn ngay với `HTTP 402 Payment Required`.
  - **Sau khi gọi LLM (`record_cost`):** Tính chi phí thực tế theo số input/output tokens (`(in/1000)*0.00015 + (out/1000)*0.0006`) và cộng dồn nguyên tử bằng `r.incrbyfloat(key, cost)` kèm `r.expire(...)` để tự reset sang chu kỳ mới.
- **Vì sao cần cả Rate Limit lẫn Cost Guard:**
  - **Rate Limit** bảo vệ **tốc độ/hạ tầng** (chống DDoS, spam request/phút làm nghẽn CPU/worker).
  - **Cost Guard** bảo vệ **ngân sách tiền API LLM** (vì 10 request/phút với prompt rất dài vẫn có thể đốt hết tiền dù không vượt rate limit).

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Liveness (`/health`) vs Readiness (`/ready`)

- **`GET /health` (Liveness probe):** Trả lời câu hỏi *"Process còn sống không?"*. Chỉ kiểm tra tiến trình app đang phản hồi HTTP `200`, **không** phụ thuộc vào Redis/DB ngoài. Nếu `/health` fail, platform (Docker, Cloud Run, Kubernetes) sẽ **restart container**.
- **`GET /ready` (Readiness probe):** Trả lời câu hỏi *"Instance đã sẵn sàng nhận traffic chưa?"*. Kiểm tra kết nối tới các dependency thiết yếu (như `redis_healthy()` / DB) và trạng thái khởi động/shutdown. Nếu mất Redis, trả `503 Service Unavailable` để Load Balancer tạm ngừng đẩy traffic vào instance đó **mà không restart nhầm container**.

### Exercise 5.2: Graceful Shutdown (`SIGTERM`)

- Khi scale down hoặc deploy phiên bản mới, orchestrator gửi tín hiệu **`SIGTERM`** trước khi ép tắt bằng `SIGKILL`.
- Ứng dụng gắn lifecycle `lifespan` + chuyển tiếp signal `SIGTERM` về handler của `uvicorn` để:
  1. Ngừng nhận kết nối mới (và đánh dấu chưa sẵn sàng).
  2. Chờ các request đang xử lý (in-flight requests) hoàn thành trọn vẹn và trả `200`.
  3. Đóng kết nối Redis/DB rồi mới thoát êm với exit code `0`.

### Exercise 5.3–5.5: Stateless Design & Load Balancing với 3 Agent Instances + Redis + Nginx

- **Vì sao state trong RAM hỏng khi scale ngang:** Mỗi container/worker có vùng nhớ RAM riêng. Nếu lưu `conversation_history` hoặc bộ đếm rate limit trong dict trên RAM, Request 1 vào `instance-1` và Request 2 được Load Balancer đưa sang `instance-2` sẽ không thấy dữ liệu của nhau (mất lịch sử hội thoại, sai bộ đếm rate limit).
- **Giải pháp:** Chuyển toàn bộ shared state (session history, rate limit, budget cost) ra **Redis** dùng chung, giúp mọi instance đều stateless và thay thế/scale ngang tự do.

**Kết quả chạy thực tế (`docker compose -p k5-day14-scaling up -d --build --scale agent=3` + `python test_stateless.py`):**
```text
Session ID: c9904dcc-bd7b-41bb-8305-7366bca04c09

Request 1: [instance-e4d062] -> Q: What is Docker?
Request 2: [instance-477149] -> Q: Why do we need containers?
Request 3: [instance-e977e3] -> Q: What is Kubernetes?
Request 4: [instance-e4d062] -> Q: How does load balancing work?
Request 5: [instance-477149] -> Q: What is Redis used for?

Total requests: 5
Instances used: {'instance-477149', 'instance-e977e3', 'instance-e4d062'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
✅ Session history preserved across all instances via Redis!
```
**Giải thích:** Nginx phân phối 5 request luân phiên qua cả 3 container (`instance-e4d062`, `instance-477149`, `instance-e977e3`), nhưng cuối phiên vẫn truy xuất đủ **10 tin nhắn** (5 cặp user/assistant) vì toàn bộ lịch sử hội thoại được lưu tập trung trong Redis.

---

## Part 6: Final Project — Kết quả `check_production_ready.py`

Chạy kiểm tra đầy đủ (tĩnh + runtime + Docker + POSIX `SIGTERM`) trong `06-lab-complete/`:

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

*(Chi tiết đo thực tế: image multi-stage nặng `238 MB` < `500 MB`, `SIGTERM` lúc có request in-flight vẫn trả `200` và thoát với exit code `0`, `docker stop` hoàn tất trong `3.0s` với exit code `0`.)*

---

## AI Usage Log

- **Công cụ:** Antigravity AI Assistant
- **Cách sử dụng:**
  - **CP0 & CP1:** Phân tích cấu trúc dự án, kiểm tra môi trường Docker/Python, đối chiếu anti-patterns giữa `01-localhost-vs-production/develop/app.py` và `production/app.py`, chạy kiểm thử thực tế các endpoint và tổng hợp nội dung Part 1 vào `MISSION_ANSWERS.md`.
  - **CP2 (Part 2: Docker):** Hỗ trợ chạy build và đo dung lượng thực tế `my-agent:develop` (1.67 GB) vs `my-agent:advanced` (240 MB, -85.62%), chạy test Docker Compose stack qua Nginx và ghi chép câu trả lời vào `MISSION_ANSWERS.md`.
  - **CP3 (Part 4: API Security):** Hỗ trợ chạy kiểm thử xác thực API Key (`401`/`200`), JWT `/auth/token`, vòng lặp Rate Limit (`429`) và tổng hợp giải thích Cost Guard với Redis vào `MISSION_ANSWERS.md`.
  - **CP4 (Part 5: Scaling & Reliability):** Chạy Compose `--scale agent=3` kèm `test_stateless.py`, phân tích phân phối tải qua 3 instance & session lưu trên Redis vào `MISSION_ANSWERS.md`.
  - **CP5 (Part 6: Final Project):** Hoàn thiện các `TODO` trong `06-lab-complete/` (`config.py`, `redis_client.py`, `auth.py`, `rate_limiter.py`, `cost_guard.py`, `main.py`, `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.env.example`, `railway.toml`, `render.yaml`) và kiểm chứng đạt **`PASS 12/12` (43/43 checks)** trong môi trường Linux POSIX + Docker.
  - **CP6 (Part 3: Cloud Deployment):** Soạn sẵn `DEPLOYMENT.md`, bảng so sánh `railway.toml` vs `render.yaml`, và mô tả pipeline CI/CD GCP Cloud Run.
  - **CP7 & CP8 (Part 7: Benchmark & Observability):** Thêm Histogram `agent_question_length_chars`, bổ sung 2 mục còn thiếu vào `KNOWLEDGE_BASE` để đạt eval 23/23 (100%), tạo workflow `.github/workflows/eval.yml`, chạy `promtool` + Locust `scale_1`/`scale_3` + thí nghiệm chaos trigger 3 Prometheus alerts cùng firing, trích xuất trace/log Jaeger và hoàn thiện `BENCHMARK_REPORT.md` khớp hoàn toàn với dữ liệu JSON/CSV thực đo.
