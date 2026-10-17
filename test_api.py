import requests

url = "http://127.0.0.1:8000/api/ai/diagnose"
data = {"symptoms": "xe không thể khởi động"}

try:
    response = requests.post(url, json=data)
    with open('test_output.txt', 'w', encoding='utf-8') as f:
        f.write(f"Status Code: {response.status_code}\n")
        f.write(f"Response Text: {response.text}\n")
except Exception as e:
    print("Error:", e)
