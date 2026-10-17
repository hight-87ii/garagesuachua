import datetime
import random
from sqlalchemy.orm import Session
from app.models.models import DailyWeather
# from app.services.gemini_service import get_gemini_response

async def fetch_and_store_daily_weather(db: Session, location: str = "Hanoi"):
    """
    Giả lập việc gọi API thời tiết (ví dụ: OpenWeatherMap).
    Trong thực tế, bạn sẽ dùng thư viện httpx hoặc requests để lấy JSON từ API.
    """
    today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    
    # Kiểm tra xem hôm nay đã lấy thời tiết chưa
    existing = db.query(DailyWeather).filter(DailyWeather.date == today_str).first()
    if existing:
        return existing

    # Mock data thời tiết
    conditions = ["Trời nắng gắt", "Mưa rào", "Nhiều mây", "Mưa phùn", "Nắng nhẹ", "Bão"]
    current_condition = random.choice(conditions)
    temp = random.uniform(20.0, 40.0)
    humidity = random.uniform(40.0, 95.0)
    rainfall = random.uniform(0.0, 50.0) if "Mưa" in current_condition or "Bão" in current_condition else 0.0
    aqi = random.randint(30, 200)

    # Sinh prompt để AI tổng hợp lời khuyên cho Gara dựa trên thời tiết
    prompt = f"""
    Bạn là một chuyên gia kỹ thuật AI của gara ô tô.
    Thời tiết hôm nay tại {location} là: {current_condition}.
    Nhiệt độ: {temp:.1f} độ C. Độ ẩm: {humidity:.1f}%. Lượng mưa: {rainfall} mm. Chỉ số AQI: {aqi}.
    Dựa trên thời tiết này, hãy đưa ra 3 lời khuyên ngắn gọn để gara tư vấn cho khách hàng đến bảo dưỡng xe hôm nay.
    Ví dụ: Nếu trời mưa, khuyên khách kiểm tra gạt mưa, lốp. Nếu trời nắng nóng, kiểm tra điều hòa, nước làm mát.
    """
    
    # Ở đây giả lập gọi hàm AI sinh lời khuyên (vì tôi đang không kết nối db/API trực tiếp)
    # ai_advice = await get_gemini_response(prompt)
    ai_advice = "1. Kiểm tra hệ thống điều hòa do nhiệt độ bất thường.\n2. Kiểm tra áp suất lốp.\n3. Vệ sinh lọc gió động cơ do AQI cao." if aqi > 150 else "1. Nhắc khách hàng rửa xe sau những ngày mưa.\n2. Kiểm tra lốp và phanh."

    weather_record = DailyWeather(
        date=today_str,
        temperature=temp,
        humidity=humidity,
        rainfall=rainfall,
        air_quality_aqi=aqi,
        weather_condition=current_condition,
        ai_daily_advice=ai_advice
    )
    db.add(weather_record)
    db.commit()
    db.refresh(weather_record)
    
    return weather_record

def get_today_weather_context(db: Session) -> str:
    """Hàm này sẽ được ghép vào Prompt của các Agent khác (ví dụ: Technical Agent, Customer Agent)"""
    today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    weather = db.query(DailyWeather).filter(DailyWeather.date == today_str).first()
    
    if not weather:
        return "Không có dữ liệu thời tiết hôm nay."
        
    context = (f"Thông tin thời tiết hôm nay ({weather.date}): {weather.weather_condition}, "
               f"Nhiệt độ {weather.temperature:.1f}°C, Độ ẩm {weather.humidity:.1f}%, "
               f"Mưa {weather.rainfall}mm, AQI {weather.air_quality_aqi}. "
               f"Lời khuyên AI hôm nay: {weather.ai_daily_advice}")
    return context
