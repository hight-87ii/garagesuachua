import pandas as pd
import joblib
import os
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

def train_and_save_model():
    # 1. Tải dữ liệu
    data_path = "data/garage_data.csv"
    if not os.path.exists(data_path):
        print("Không tìm thấy dữ liệu. Hãy chạy 'python data_generator.py' trước.")
        return

    df = pd.read_csv(data_path)
    
    # Chia input (X) và output (y)
    X = df['symptoms']
    y = df['category']
    
    # 2. Chia tập Train và Test (80% train, 20% test để đánh giá)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # 3. Tạo Pipeline: 
    # TfidfVectorizer: Biến đổi câu chữ thành các con số (tần suất từ)
    # MultinomialNB: Thuật toán Naive Bayes siêu nhanh để phân loại chữ
    model_pipeline = make_pipeline(TfidfVectorizer(), MultinomialNB())
    
    print("Đang huấn luyện mô hình AI...")
    # 4. Huấn luyện (Dạy cho AI)
    model_pipeline.fit(X_train, y_train)
    
    # 5. Đánh giá độ chính xác của AI trên tập Test
    y_pred = model_pipeline.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"\nĐộ chính xác (Accuracy): {acc * 100:.2f}%")
    print("\nChi tiết (Classification Report):")
    print(classification_report(y_test, y_pred))
    
    # 6. Lưu mô hình ra file để ứng dụng Web xài lại
    os.makedirs("models", exist_ok=True)
    joblib.dump(model_pipeline, "models/garage_ai_model.pkl")
    print("\nĐã lưu bộ não AI tại: models/garage_ai_model.pkl")
    
    # Lưu thêm từ điển dữ liệu để mapping
    diagnosis_map = df.drop_duplicates('category').set_index('category').to_dict('index')
    joblib.dump(diagnosis_map, "models/diagnosis_map.pkl")
    print("Đã lưu từ điển lời khuyên tại: models/diagnosis_map.pkl")

if __name__ == "__main__":
    train_and_save_model()
