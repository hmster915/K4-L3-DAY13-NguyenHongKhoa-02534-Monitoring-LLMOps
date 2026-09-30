# Báo cáo cá nhân — K4-L3B Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:**
- **MSSV:**
- **Lớp:** K4-L3B
- **Repository URL:**
- **Commit SHA cuối:**
- **Challenge ID:**
- **Tên project Langfuse cá nhân:** `day13-k4-l3b-<MSSV>`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.png` |
| Log validator | `evidence/02-log-validator.txt` |
| Dashboard validator | `evidence/03-dashboard-validator.txt` |
| Structured log | `evidence/04-structured-log.txt` |
| PII redaction | `evidence/05-pii-redaction.txt` |
| Trace list | `evidence/06-trace-list.txt` |
| Trace waterfall | `evidence/07-trace-waterfall.txt` |
| Trace metadata | `evidence/08-trace-metadata.txt` |
| Prompt versions | `evidence/09-prompt-versions.txt` |
| Prompt rollback | `evidence/10-prompt-rollback.txt` |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.png` |
| Incident trace | `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 | 100/100 | 11 correlation IDs, đầy đủ metadata, không phát hiện PII thô |
| `validate_dashboard.py` | 6/6 contract | 6/6 contract + dashboard runtime | Sáu panel dùng dữ liệu thật từ `data/logs.jsonl` |
| `pytest` | 22 passed | 27 passed | Bổ sung test correlation ID, context isolation và bốn loại PII |
| Số traces hợp lệ | Chưa có child observations | 14 | Mỗi trace có agent, retrieval và generation |
| Số PII leak | 0 | 0 | Kiểm tra runtime với email, điện thoại, CCCD và thẻ giả |
| Latency P95 / TTFT P95 | | 5369 ms / 51 ms | Cửa sổ dashboard 60 phút, gồm các request setup/cold-start |
| Retrieval success rate | | 100% | Không có retrieval failure trong workload CP2 |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** Middleware xóa context cũ ở đầu mỗi request, nhận `x-request-id` hợp lệ theo dạng `req-<8-hex>` hoặc sinh ID mới từ UUID. ID được bind vào structlog context, lưu trong `request.state`, trả lại ở response body/header và dùng để nối log với trace.
- **Các metadata được ghi vào structured log:** `user_id_hash`, `session_id`, `feature`, `model`, `env` và `correlation_id`, bên cạnh `ts`, `level`, `service`, `event` cùng các số liệu latency/token/cost/quality khi có.
- **Cách bảo đảm PII được scrub trước khi ghi:** `scrub_event` duyệt đệ quy chuỗi trong event và được đăng ký trước `JsonlFileProcessor` và `JSONRenderer`, nên email, điện thoại Việt Nam, CCCD và thẻ thanh toán được che trước khi serialize/ghi file.
- **Cách kiểm chứng kết quả:** Chạy unit/integration tests, gửi request runtime chứa bốn loại PII giả và chạy `python scripts/validate_logs.py`. Kết quả CP1 đạt 100/100, 11 correlation ID hợp lệ, không thiếu enrichment và không phát hiện PII thô.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** Tôi truy vấn Observations API v2 của project `day13-k4-l3b-02534`, nhóm observation theo `trace_id` và chỉ tính trace có đủ `lab-agent-run`, `retrieval`, `generation`. Kết quả có 14 trace tree hợp lệ.
- **Cấu trúc root/retrieval/generation observations:** `lab-agent-run` loại AGENT là root; `retrieval` loại RETRIEVER và `generation` loại GENERATION là hai child cùng parent. Generation có model, managed prompt, token usage và cost.
- **Cách nối trace với log:** `correlation_id` được bind trong middleware, ghi vào structured log và propagation metadata của mọi observation. Ví dụ `req-8f3e2d6a` nối log với trace `8cd4a2894fa0a749869ed838e76de1c7`.
- **Prompt name:** `day13-chat`
- **Version/label baseline:** version 1, labels cuối cùng `baseline`, `production`
- **Version/label candidate:** version 2, labels cuối cùng `candidate`, `latest`
- **Trace ID của mỗi version:** baseline `84e4019c274135a8c4e2d7294f64d92e`; candidate `7a022e190e3ab0cd8cb43fd67609552a`
- **Cách promote và rollback `production`:** Dùng Langfuse label update để chuyển `production` sang v2, tạo trace `f030b3ea8371f4bb787cf4c7e443bf09`, sau đó chuyển `production` về v1 và tạo trace `a5bdd83e13d3915c8c807017618969b1`. Ứng dụng luôn fetch theo label nên không cần đổi code.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** Runtime tại `/dashboard` đọc trực tiếp `data/logs.jsonl`, lọc cửa sổ 60 phút và tự refresh 30 giây. Sáu panel gồm latency P50/P95/P99 + TTFT P95, traffic, error/retrieval, cost, tokens và quality; mỗi panel có đơn vị cùng threshold.
- **SLO và lý do chọn:** 99.5% request trong cửa sổ 28 ngày phải có `response_sent` và latency không quá 3000 ms. Ngưỡng 3 giây là giới hạn trải nghiệm người dùng trong dashboard contract; 99.5% vẫn cho phép số ít cold-start/dependency failure nhưng yêu cầu luồng bình thường ổn định.
- **Cách tính error budget:** `100% - 99.5% = 0.5%`. Với 10,000 request trong 28 ngày, tối đa 50 request được phép lỗi hoặc chậm hơn 3000 ms.
- **Ba alert và runbook tương ứng:** `HighLatencyP95` (>3000 ms trong 5m), `HighRequestErrorRate` (>2% trong 5m), `LowRetrievalSuccessRate` (<90% trong 10m). Cả ba gửi Slack `#k4-l3b-alerts`, owner `student-02534` và có runbook Metrics → Logs → Traces trong `docs/alerts.md`.

> Ví dụ cách viết error budget: "SLO 99.5% trong 28 ngày nghĩa là error budget 0.5%. Nếu workload có 10,000 request thì tối đa 50 request được phép lỗi hoặc chậm hơn ngưỡng SLO."

## 7. Điều tra challenge

- **Challenge ID:**
- **Khoảng thời gian điều tra:**
- **Triệu chứng từ metrics:**
- **Log line và correlation ID liên quan:**
- **Trace ID và span gây ảnh hưởng:**
- **Root cause:**
- **Fix action:**
- **Preventive measure:**

> Gợi ý cách viết ngắn, không thay cho evidence thực tế: "Metric cho thấy `[latency/error/cost/quality]` bất thường trong `[khoảng thời gian]`. Log line `[event]` có `correlation_id=[...]` đại diện cho request bị ảnh hưởng. Trace cùng `correlation_id` cho thấy span `[retrieval/generation/prompt/tool]` có dấu hiệu `[chậm/lỗi/token tăng]`. Root cause là `[nguyên nhân suy ra từ evidence]`. Fix action là `[hành động khôi phục]`; preventive measure là `[alert/runbook/test/guardrail để ngăn tái diễn]`."

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:**
- **Một lỗi/blocker đã gặp:**
- **Cách tìm nguyên nhân và xử lý:**
- **Cách hiểu luồng Metrics → Logs → Traces:**
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:**
- **Điều quan trọng nhất đã học:**
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
