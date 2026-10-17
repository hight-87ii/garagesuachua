from app.services.gemini_service import get_gemini_response

try:
    print("Testing gemini_service...")
    res = get_gemini_response("Xe tôi bị kêu lạch cạch ở gầm", [], "Test context")
    print("Response:", res)
except Exception as e:
    print("Exception:", e)
