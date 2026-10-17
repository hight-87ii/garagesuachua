import os
import joblib

# Đường dẫn tới thư mục lưu mô hình
MODEL_PATH = "models/garage_ai_model.pkl"
MAP_PATH = "models/diagnosis_map.pkl"

# Biến lưu trữ mô hình trên bộ nhớ (để không phải đọc file lại từ đầu mỗi lần gọi API)
_model = None
_map = None

def load_ai_model():
    """Hàm tải mô hình AI vào bộ nhớ RAM"""
    global _model, _map
    try:
        if os.path.exists(MODEL_PATH) and os.path.exists(MAP_PATH):
            _model = joblib.load(MODEL_PATH)
            _map = joblib.load(MAP_PATH)
            print("AI model loaded successfully.")
        else:
            print("Warning: AI model not found. Run train_model.py first.")
    except Exception as e:
        print(f"Error loading AI model: {e}")

# Gọi hàm load model ngay khi khởi động server
load_ai_model()

def analyze_vehicle_symptoms(symptoms: str) -> str:
    """
    Hàm này nhận mô tả lỗi (triệu chứng) từ khách hàng,
    và dùng mô hình scikit-learn (Tfidf + NaiveBayes) đã train để dự đoán bệnh.
    """
    if _model is None or _map is None:
        return "Hệ thống AI chưa sẵn sàng. Vui lòng huấn luyện mô hình (chạy file train_model.py) trước."
        
    try:
        # AI xử lý dự đoán dựa trên chữ khách hàng nhập vào
        predicted_category = _model.predict([symptoms])[0]
        
        # Tra cứu thêm lời khuyên từ bộ từ điển
        advice = _map.get(predicted_category, {})
        recommendation = advice.get('recommendation', 'Cần mang xe đến garage để kiểm tra kỹ hơn.')
        severity = advice.get('severity', 'Chưa rõ')
        
        # Trình bày kết quả trả về cho web
        result_text = f"Phân loại bệnh: {predicted_category}\n"
        result_text += f"Mức độ: {severity}\n"
        result_text += f"Lời khuyên/Dịch vụ gợi ý: {recommendation}"
        
        return result_text
        
    except Exception as e:
        return f"Lỗi trong quá trình AI phân tích: {str(e)}"
