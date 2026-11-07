import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=api_key, http_options=genai.types.HttpOptions(api_version="v1beta"))

print("Gemini에게 카드뉴스 제목 써달라고 시켜볼게요...\n")

response = client.models.generate_content(
    model="models/gemini-2.5-flash",
    contents="너는 경제 카드뉴스 작가야. '금리 인하'를 주제로 인스타 카드뉴스 후킹 제목을 2줄로, 한 줄에 6자 이내로 임팩트 있게 하나만 지어줘.",
)

print("=== Gemini 답변 ===")
print(response.text)
print("===================")
print("\n성공! Gemini가 잘 작동해요. 🎉")
