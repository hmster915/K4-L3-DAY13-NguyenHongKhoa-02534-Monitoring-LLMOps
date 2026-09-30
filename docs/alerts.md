# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert mẫu để tham khảo

Ví dụ dưới đây minh họa mức độ cụ thể cần có. Học viên không cần copy nguyên, nhưng ba alert trong bài nộp nên rõ ràng tương tự: điều kiện là gì, kéo dài bao lâu, ảnh hưởng tới user ra sao và người trực cần kiểm tra gì trước.

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: latency P95 của `response_sent.latency_ms`
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` trong 5 phút
- Ảnh hưởng tới người dùng: người dùng phải chờ lâu hơn trước khi nhận câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard latency để xác nhận P95/P99 và khoảng thời gian tăng.
  2. Lọc `data/logs.jsonl` trong khoảng đó, lấy một `correlation_id` có `latency_ms` cao.
  3. Mở trace cùng `correlation_id` trên Langfuse, so sánh các span chính để xác định bước nào bất thường.
- Mitigation tạm thời: dựa trên evidence thực tế để rollback prompt, khôi phục cấu hình liên quan, tắt practice scenario hoặc giảm tải khi demo.
- Owner: `student-<MSSV>`

## Alert 1

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: latency P95 của các event `response_sent`
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` liên tục trong 5 phút
- Ảnh hưởng tới người dùng: phần lớn request vẫn chạy nhưng nhóm request chậm nhất phải chờ quá ngưỡng trải nghiệm 3 giây.
- Ba bước kiểm tra đầu tiên:
  1. Mở panel Latency, xác nhận P95/P99, TTFT và khoảng thời gian bắt đầu tăng.
  2. Lọc `data/logs.jsonl` theo khoảng thời gian, chọn một `response_sent` có `latency_ms > 3000` và lấy `correlation_id`.
  3. Mở trace cùng `correlation_id` trên Langfuse, so sánh span retrieval và generation để xác định bước chậm.
- Mitigation tạm thời: rollback prompt nếu regression trùng với prompt version mới; nếu retrieval chậm thì tắt incident/practice scenario hoặc khôi phục cấu hình retrieval trước đó.
- Owner: `student-02534`

## Alert 2

- Tên: `HighRequestErrorRate`
- Severity: `critical`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: tỷ lệ `request_failed` trên tổng `request_received`
- Điều kiện và thời gian duy trì: error rate lớn hơn 2% liên tục trong 5 phút
- Ảnh hưởng tới người dùng: request trả lỗi thay vì câu trả lời, trực tiếp tiêu thụ error budget của SLO.
- Ba bước kiểm tra đầu tiên:
  1. Mở panel Errors để xác nhận error rate và breakdown theo `error_type`.
  2. Lọc một `request_failed` đại diện trong `data/logs.jsonl`, ghi lại `correlation_id`, `error_type` và thời điểm.
  3. Mở trace cùng `correlation_id`, xác định span lỗi và kiểm tra trạng thái retrieval/generation.
- Mitigation tạm thời: tắt scenario gây lỗi, rollback cấu hình hoặc prompt vừa thay đổi; nếu dependency lỗi thì chuyển sang fallback đã kiểm chứng.
- Owner: `student-02534`

## Alert 3

- Tên: `LowRetrievalSuccessRate`
- Severity: `warning`
- Duration: `10m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: tỷ lệ thành công của tool retrieval
- Điều kiện và thời gian duy trì: retrieval success thấp hơn 90% liên tục trong 10 phút
- Ảnh hưởng tới người dùng: câu trả lời có thể thiếu context, giảm chất lượng hoặc request có thể thất bại hoàn toàn.
- Ba bước kiểm tra đầu tiên:
  1. Mở panel Errors, xác nhận retrieval success và so sánh với error rate/quality proxy.
  2. Lọc các event có `tool_name=retrieval` và `tool_success=false`, lấy một `correlation_id` đại diện.
  3. Mở trace tương ứng và kiểm tra span retrieval, thời lượng, status và output đã scrub.
- Mitigation tạm thời: khôi phục retrieval config/index ổn định, dùng fallback context an toàn và giảm rollout cho tới khi success rate phục hồi.
- Owner: `student-02534`
