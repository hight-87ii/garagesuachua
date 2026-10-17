import logging
import os
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

logger = logging.getLogger("threeh.gemini")

MODEL = "gemini-3.8-flash"
TIMEOUT_S = 20
MAX_RETRIES = 2
# Fail-fast: quota/503 tra ngay, khong retry/sleep (do retry cung loi + bat user doi).
# Chi retry 1 lan cho loi transient 504/DEADLINE.
RETRYABLE_MARKERS = ("504", "DEADLINE")
NO_RETRY_MARKERS = ("429", "Quota", "quota", "503", "UNAVAILABLE")

NO_KEY_MSG = "Lỗi: Chưa cấu hình GEMINI_API_KEY trong file .env."
OVERLOAD_MSG = "Hệ thống AI hiện đang quá tải do nhu cầu cao. Bạn vui lòng thử lại sau vài phút nhé."
QUOTA_MSG = "Hệ thống AI đã vượt quá giới hạn truy cập. Bạn vui lòng thử lại sau nhé."
CONN_ERR_MSG = "Xin lỗi, AI đang gặp sự cố kết nối. Vui lòng thử lại sau."
GENERIC_ERR_MSG = "Xin lỗi, đã có lỗi xảy ra. Vui lòng thử lại sau."

if api_key:
    client = genai.Client(api_key=api_key, http_options={"timeout": TIMEOUT_S * 1000})
else:
    client = None


def _format_history(history: list) -> list:
    """Convert [{sender, text}] -> [Content]. Dùng chung cho cả 2 hàm."""
    formatted = []
    if history:
        for msg in history:
            role = "user" if msg.get("sender") == "user" else "model"
            formatted.append(
                types.Content(role=role, parts=[types.Part.from_text(text=msg.get("text", ""))])
            )
    return formatted


def _system_config(context_msg: str):
    """System prompt TV + context_msg inject. Dùng chung cho cả 2 hàm."""
    return types.GenerateContentConfig(
        system_instruction=(
            "Bạn là trợ lý AI (chuyên gia) của Garage ThreeH Workshop. "
            "Thông tin cơ bản của Garage: Địa chỉ tại Tháp đôi Prime Thái Nguyên, số 1 Hoàng Văn Thụ, Phan Đình Phùng, Thái Nguyên. Hotline: 0981.888.888. "
            "Hãy trả lời thân thiện, chuyên nghiệp và đúng ngôn ngữ của người dùng. "
            f"Ngữ cảnh hiện tại: {context_msg} "
            "Lưu ý: Nếu có tài liệu hướng dẫn nội bộ trong Ngữ cảnh, hãy ưu tiên sử dụng để trả lời. Không lặp lại lời chào dài dòng. "
            "QUAN TRỌNG: Hãy trả lời bằng văn bản thuần túy (Plain Text). TUYỆT ĐỐI KHÔNG sử dụng các ký tự Markdown như dấu sao (*) để in đậm hay tạo danh sách, và dấu thăng (#) để làm tiêu đề. "
            "Trả lời tối đa 150 từ, đúng 3 mục: 1.Nhận định (gắn biển số + lần sửa trước nếu có) "
            "2.Việc làm ngay (tối đa 3 ý) 3.Khi nào mang tới xưởng + giá tham khảo. "
            "Không chào dài. Nếu tài liệu nội bộ trống thì bỏ qua, không bịa."
        ),
        temperature=0.7,
        top_p=0.9,
        max_output_tokens=600,
    )


def _chat_once(message: str, history: list, context_msg: str):
    """Tạo chat object (model + config + history). Dùng chung cho cả 2 hàm."""
    return client.chats.create(
        model=MODEL,
        config=_system_config(context_msg),
        history=_format_history(history),
    )


def _is_retryable(err_str: str, attempt: int) -> bool:
    if any(m in err_str for m in NO_RETRY_MARKERS):
        return False
    return any(m in err_str for m in RETRYABLE_MARKERS) and attempt < MAX_RETRIES - 1


def _sleep_backoff(attempt: int) -> None:
    # Fail-fast: chi 1 sleep ngan cho transient (MAX_RETRIES=2 -> toi da 1 lan).
    time.sleep(1.0)


def _map_error(err_str: str) -> str:
    if "503" in err_str or "UNAVAILABLE" in err_str:
        return OVERLOAD_MSG
    if "429" in err_str or "Quota" in err_str:
        return QUOTA_MSG
    return CONN_ERR_MSG


def _strip_markdown(text: str) -> str:
    """Bóc ``` fences + ký tự * # (như main.py chatbot). Idempotent."""
    t = (text or "").strip()
    if t.startswith("```html"):
        t = t[7:]
    if t.startswith("```"):
        t = t[3:]
    if t.endswith("```"):
        t = t[:-3]
    return t.replace("*", "").replace("#", "").strip()


def get_gemini_response(message: str, history: list, context_msg: str) -> str:
    if not client:
        return NO_KEY_MSG

    try:
        chat = _chat_once(message, history, context_msg)
        for attempt in range(MAX_RETRIES):
            try:
                response = chat.send_message(message)
                return _strip_markdown(response.text or "")
            except Exception as e:
                err_str = str(e)
                if _is_retryable(err_str, attempt):
                    _sleep_backoff(attempt)
                    continue
                return _map_error(err_str)
    except Exception as e:
        logger.warning("get_gemini_response failed: %s", e)
        return GENERIC_ERR_MSG


def get_gemini_response_stream(message: str, history: list, context_msg: str):
    if not client:
        yield NO_KEY_MSG
        return

    try:
        chat = _chat_once(message, history, context_msg)
        for attempt in range(MAX_RETRIES):
            try:
                response_stream = chat.send_message_stream(message)
                for chunk in response_stream:
                    if chunk.text:
                        yield _strip_markdown(chunk.text)
                return  # Exit successfully if the stream finishes
            except Exception as e:
                err_str = str(e)
                if _is_retryable(err_str, attempt):
                    _sleep_backoff(attempt)
                    # Note: retrying re-sends the whole message; acceptable for chat.
                    continue
                yield _map_error(err_str)
                return
    except Exception as e:
        logger.warning("get_gemini_response_stream failed: %s", e)
        yield GENERIC_ERR_MSG
