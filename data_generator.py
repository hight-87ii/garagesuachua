import pandas as pd
import random
import os

# Tập dữ liệu giả lập về các triệu chứng thường gặp và chẩn đoán bệnh
DIAGNOSIS_DATA = {
    "Hệ thống Lái & Bánh xe": {
        "symptoms": [
            "xe bị rung vô lăng khi chạy tốc độ cao",
            "tay lái nặng, khó đánh lái",
            "khi ôm cua nghe tiếng kêu lụp cụp dưới gầm",
            "xe bị xỉa lái sang một bên khi đi thẳng",
            "lốp mòn không đều, ăn lốp một bên",
            "xe bị lắc lư khi đi qua gờ giảm tốc"
        ],
        "recommendation": "Gói kiểm tra gầm, cân bằng động mâm vỏ và cân chỉnh thước lái.",
        "severity": "Trung bình"
    },
    "Hệ thống Phanh": {
        "symptoms": [
            "đạp phanh kêu két két",
            "phanh bị rít",
            "đạp phanh sâu mới ăn",
            "chân phanh bị rung khi phanh gấp",
            "đèn cảnh báo ABS sáng trên taplo",
            "bố thắng có mùi khét khi xuống dốc"
        ],
        "recommendation": "Kiểm tra thay má phanh, láng dĩa phanh và châm dầu phanh.",
        "severity": "Cao (Nguy hiểm)"
    },
    "Hệ thống Động cơ & Bôi trơn": {
        "symptoms": [
            "đèn check engine sáng",
            "xe hao nhớt, ra khói trắng ở pô",
            "nổ máy buổi sáng nghe tiếng gõ cạch cạch",
            "động cơ bị hụt ga, đạp không lên",
            "xe bị rung bần bật khi dừng đèn đỏ",
            "hao xăng bất thường, mùi xăng sống"
        ],
        "recommendation": "Quét lỗi OBD-II, thay nhớt động cơ, vệ sinh kim phun buồng đốt và kiểm tra bugi.",
        "severity": "Cao"
    },
    "Hệ thống Làm mát": {
        "symptoms": [
            "kim nhiệt độ động cơ báo quá vạch giữa",
            "quạt tản nhiệt kêu to liên tục",
            "nước làm mát bị hao hụt nhanh",
            "thấy vũng nước màu xanh đỏ rỉ dưới gầm xe",
            "máy lạnh không mát khi kẹt xe"
        ],
        "recommendation": "Kiểm tra rò rỉ két nước, thay nước làm mát, vệ sinh dàn nóng máy lạnh.",
        "severity": "Cao"
    },
    "Hệ thống Điện & Bình Ắc quy": {
        "symptoms": [
            "đề máy không nổ, chỉ kêu tạch tạch",
            "đèn pha bị tối mờ khi nổ vòng tua thấp",
            "chìa khóa thông minh (smartkey) không nhận",
            "bấm còi không kêu hoặc kêu lí nhí",
            "màn hình giải trí tự khởi động lại"
        ],
        "recommendation": "Kiểm tra đo dòng bình ắc quy, kiểm tra máy phát điện (dynamo).",
        "severity": "Thấp"
    }
}

def generate_dataset(num_samples=500):
    """
    Sinh ra một tập dữ liệu lớn bằng cách tạo thêm các biến thể nhỏ của câu.
    """
    data = []
    modifiers = ["hơi", "rất", "thỉnh thoảng", "thường xuyên", "bị", "xe tôi", "hiện tượng", "tự nhiên"]
    
    categories = list(DIAGNOSIS_DATA.keys())
    
    for _ in range(num_samples):
        cat = random.choice(categories)
        base_symptom = random.choice(DIAGNOSIS_DATA[cat]["symptoms"])
        
        # Thêm từ khóa biến thể để dữ liệu đa dạng hơn
        if random.random() > 0.5:
            mod = random.choice(modifiers)
            text = f"{mod} {base_symptom}"
        else:
            text = base_symptom
            
        data.append({
            "symptoms": text,
            "category": cat,
            "recommendation": DIAGNOSIS_DATA[cat]["recommendation"],
            "severity": DIAGNOSIS_DATA[cat]["severity"]
        })
        
    df = pd.DataFrame(data)
    
    # Đảm bảo thư mục data tồn tại
    os.makedirs("data", exist_ok=True)
    df.to_csv("data/garage_data.csv", index=False, encoding="utf-8-sig")
    print(f"Đã tạo {num_samples} mẫu dữ liệu tại data/garage_data.csv")

if __name__ == "__main__":
    generate_dataset()
