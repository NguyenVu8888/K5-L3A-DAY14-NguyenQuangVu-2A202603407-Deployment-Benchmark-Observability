# Deployment Information

> **Lưu ý cho Vũ:** Sau khi chạy `railway up` (hoặc deploy Render Blueprint) trong thư mục `06-lab-complete/`, hãy thay `<YOUR_PUBLIC_URL>` và `<YOUR_API_KEY>` (khi chạy test) rồi chụp 3 ảnh lưu vào `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png`.

## Public URL
`<YOUR_PUBLIC_URL>` *(điền sau khi deploy `06-lab-complete/` lên Railway/Render)*

## Platform
Railway (hoặc Render) — triển khai trực tiếp từ thư mục `06-lab-complete/` kèm managed Redis service.

## Test Commands

### 1. Health Check (`/health` → 200)
```bash
BASE="<YOUR_PUBLIC_URL>"
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
# Expected: 200
curl -sS "$BASE/health"
# Expected: {"status":"ok","environment":"production"}
```

### 2. Readiness Check (`/ready` → 200)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
# Expected: 200
curl -sS "$BASE/ready"
# Expected: {"status":"ready"}
```

### 3. Authentication Check (`/ask` không có key → 401)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Hello"}'
# Expected: 401
```

### 4. API Test (`/ask` có `X-API-Key` → 200)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
# Expected: 200
```

## Environment Variables Set (trên Cloud Dashboard — không ghi secret vào repo)
- `PORT` (do nền tảng tự động inject)
- `ENVIRONMENT=production`
- `AGENT_API_KEY` (đặt secret trên Railway/Render dashboard)
- `REDIS_URL` (trỏ tới Redis service của Railway/Render)
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
