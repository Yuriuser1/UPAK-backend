import os
import io
import base64
import logging

from dotenv import load_dotenv
load_dotenv()  # Должно идти ПЕРЕД использованием os.getenv

import uuid

from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import openai
import requests
import gspread
from PIL import Image
from rembg.bg import remove
from oauth2client.service_account import ServiceAccountCredentials
from fastapi.responses import JSONResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import telegram
import firebase_admin
from firebase_admin import credentials, storage
from uuid import uuid4
from yookassa import Payment, Configuration

# Импорт новых модулей для аутентификации
from database import init_db
from routers import auth_router

# --- YOOKASSA НАСТРОЙКИ ---
Configuration.account_id = os.getenv("YOOKASSA_SHOP_ID")
Configuration.secret_key = os.getenv("YOOKASSA_SECRET_KEY")
YOOKASSA_RETURN_URL = os.getenv("YOOKASSA_RETURN_URL", "https://upak.space/payment/success")

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация приложения
app = FastAPI(title="UPAK Backend API", version="2.0.0")

# Настройка CORS для фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://upak.space",
        "https://www.upak.space"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Инициализация базы данных
@app.on_event("startup")
async def startup_event():
    init_db()
    logger.info("Database initialized")

# Подключение роутеров аутентификации
app.include_router(auth_router)

# Настройки OpenAI (для DALL-E)
openai.api_key = os.getenv("OPENAI_API_KEY")

# Настройки Yandex GPT
YANDEX_GPT_API_KEY = os.getenv("YANDEX_GPT_API_KEY")
YANDEX_GPT_FOLDER_ID = os.getenv("YANDEX_GPT_FOLDER_ID")
YANDEX_GPT_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

# Телеграм-бот
bot = telegram.Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
chat_id_template = os.getenv("TELEGRAM_CHAT_ID_TEMPLATE")

# Безопасный секрет для старого вебхука (если используешь)
WEBHOOK_SECRET = os.getenv("PAYMENT_WEBHOOK_SECRET")

def generate_text_with_yandex_gpt(messages, max_tokens=600):
    """
    Генерация текста через Yandex GPT API
    """
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {YANDEX_GPT_API_KEY}"
        }
        
        data = {
            "modelUri": f"gpt://{YANDEX_GPT_FOLDER_ID}/yandexgpt-lite",
            "completionOptions": {
                "stream": False,
                "temperature": 0.6,
                "maxTokens": str(max_tokens)
            },
            "messages": messages
        }
        
        response = requests.post(YANDEX_GPT_URL, headers=headers, json=data)
        response.raise_for_status()
        
        result = response.json()
        return result["result"]["alternatives"][0]["message"]["text"]
        
    except Exception as e:
        logger.error(f"Yandex GPT API error: {e}")
        raise HTTPException(status_code=500, detail="Error generating text with Yandex GPT")

# Инициализация Firebase
try:
    cred = credentials.Certificate("firebase_credentials.json")
    firebase_admin.initialize_app(cred, { 'storageBucket': os.getenv("FIREBASE_BUCKET") })
    bucket = storage.bucket()
    logger.info("Firebase initialized successfully")
except Exception as e:
    logger.error(f"Firebase init error: {e}")
    raise

# Инициализация Google Sheets
try:
    gs_creds = ServiceAccountCredentials.from_json_keyfile_name(
        "credentials.json", [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    gs = gspread.authorize(gs_creds)
    sheet = gs.open("UPAK_Orders").sheet1
    logger.info("Google Sheets connected successfully")
except Exception as e:
    logger.error(f"Google Sheets init error: {e}")
    raise

# --- ENDPOINT: СОЗДАНИЕ ПЛАТЕЖА через YooKassa ---
class CreatePaymentRequest(BaseModel):
    order_id: str
    amount: float  # сумма в рублях
    description: str
    telegram_id: Optional[str] = None

class CreatePaymentResponse(BaseModel):
    payment_id: str
    confirmation_url: str

@app.post("/create_payment", response_model=CreatePaymentResponse)
def create_payment(data: CreatePaymentRequest):
    """
    Создание платежа через YooKassa.
    """
    try:
        payment = Payment.create({
            "amount": {
                "value": f"{data.amount:.2f}",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": YOOKASSA_RETURN_URL
            },
            "capture": True,
            "description": data.description,
            "metadata": {
                "order_id": data.order_id,
                "telegram_id": data.telegram_id or ""
            }
        }, idempotency_key=str(uuid.uuid4()))
        return {
            "payment_id": payment.id,
            "confirmation_url": payment.confirmation.confirmation_url
        }
    except Exception as e:
        logger.error(f"YooKassa error: {e}")
        raise HTTPException(status_code=500, detail="Ошибка оплаты (YooKassa)")

# --- ENDPOINT: ПРИЕМ WEBHOOK ОТ YOOKASSA ---
@app.post("/yookassa-webhook")
async def yookassa_webhook(request: Request):
    try:
        payload = await request.json()
        event = payload.get("event")
        obj = payload.get("object", {})

        if event == "payment.succeeded":
            payment_id = obj.get("id")
            metadata = obj.get("metadata", {})
            order_id = metadata.get("order_id")
            telegram_id = metadata.get("telegram_id")

            # Обновить заказ в Google Sheets (поиск по order_id)
            if order_id:
                try:
                    cell = sheet.find(order_id)
                    # Пример: 10=payment_id, 11=pdf_url, 12=status
                    sheet.update_cell(cell.row, 9, payment_id)   # payment_id
                    sheet.update_cell(cell.row, 11, "paid")      # статус
                    row = sheet.row_values(cell.row)
                    pdf_url = row[9]  # проверь правильный столбец для pdf_url
                except Exception as e:
                    logger.error(f"Google Sheets update error: {e}")
                    raise HTTPException(status_code=500, detail="Order not found in Google Sheets")
            else:
                logger.error("No order_id in webhook")
                raise HTTPException(status_code=400, detail="No order_id in webhook")

            # Уведомление в Telegram
            if telegram_id and pdf_url:
                try:
                    bot.send_message(
                        chat_id=int(telegram_id),
                        text=f"Ваш заказ {order_id} оплачен! PDF: {pdf_url}"
                    )
                except Exception as e:
                    logger.error(f"Telegram notify error: {e}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing error")

# --- Модель запроса заказа ---
class OrderRequest(BaseModel):
    product_name: str
    product_features: str
    platform: str
    image_data: Optional[str]
    payment_id: Optional[str]
    telegram_user_id: Optional[int]

@app.post("/order")
async def create_order(data: OrderRequest):
    try:
        order_id = f"Z{sheet.row_count + 1:05d}"
        logger.info(f"Creating order {order_id}")

        # Генерация текста через Yandex GPT
        messages = [
            {"role": "system", "content": "Вы создаёте карточку для WB/Ozon."},
            {"role": "user", "content": (
                f"Товар: {data.product_name}. "
                f"Характеристики: {data.product_features}."
            )}
        ]
        try:
            content = generate_text_with_yandex_gpt(messages, 600)
            title, description = content.split("\n", 1)
        except Exception as e:
            logger.error(f"Yandex GPT text generation error: {e}")
            raise HTTPException(status_code=500, detail="Error generating product text")

        # Обработка пользовательского изображения
        user_image_url = None
        user_blob_name = None
        if data.image_data:
            try:
                img_bytes = base64.b64decode(data.image_data)
                img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
                img = remove(img)
                size = (1000,1000) if data.platform == "ozon" else (900,1200)
                img = img.resize(size)
                img_io = io.BytesIO()
                img.save(img_io, format="PNG")
                img_io.seek(0)
                user_blob_name = f"images/{order_id}_{uuid4().hex}.png"
                blob = bucket.blob(user_blob_name)
                blob.upload_from_file(img_io, content_type="image/png")
                user_image_url = blob.generate_signed_url(expiration=3600 * 24 * 7)
            except Exception as e:
                logger.error(f"Image processing error: {e}")
                # продолжаем без пользовательского изображения

        # Генерация оптимального изображения через DALL·E
        generated_image_urls: List[str] = []
        gen_blob_name = None
        try:
            prompt_base = (
                f"High-quality product photo of {data.product_name}, "
                f"{data.product_features} on a clean white background for {data.platform} listing"
            )
            img_resp = openai.Image.create(
                prompt=prompt_base,
                n=1,
                size="1024x1024",
                response_format="b64_json"
            )
            gen_bytes = base64.b64decode(img_resp.data[0].b64_json)
            gen_blob_name = f"images/generated/{order_id}_{uuid4().hex}.png"
            blob = bucket.blob(gen_blob_name)
            blob.upload_from_string(gen_bytes, content_type="image/png")
            generated_image_urls.append(blob.generate_signed_url(expiration=3600 * 24 * 7))
        except Exception as e:
            logger.error(f"Image generation error: {e}")

        # Генерация PDF с текстом и изображениями
        try:
            pdf_io = io.BytesIO()
            c = canvas.Canvas(pdf_io, pagesize=A4)
            textobject = c.beginText(40, 800)
            textobject.textLine(f"Title: {title}")
            textobject.textLines(f"Description: {description}")
            c.drawText(textobject)

            # Вставка изображений в PDF
            y_pos = 600
            if user_blob_name:
                user_bytes = bucket.blob(user_blob_name).download_as_bytes()
                c.drawImage(ImageReader(io.BytesIO(user_bytes)), 40, y_pos, width=200, height=200)
                y_pos -= 220
            if gen_blob_name:
                gen_bytes = bucket.blob(gen_blob_name).download_as_bytes()
                c.drawImage(ImageReader(io.BytesIO(gen_bytes)), 40, y_pos, width=200, height=200)
            c.showPage()
            c.save()
            pdf_io.seek(0)
            pdf_blob_name = f"pdfs/{order_id}_{uuid4().hex}.pdf"
            pdf_blob = bucket.blob(pdf_blob_name)
            pdf_blob.upload_from_file(pdf_io, content_type="application/pdf")
            pdf_url = pdf_blob.generate_signed_url(expiration=3600 * 24 * 7)
        except Exception as e:
            logger.error(f"PDF generation error: {e}")
            raise HTTPException(status_code=500, detail="Error generating PDF")

        # Сохранение данных в Google Sheets
        try:
            sheet.append_row([
                order_id,
                data.product_name,
                data.product_features,
                data.platform,
                title,
                description,
                user_image_url or "",
                ";".join(generated_image_urls),
                data.payment_id or "",
                pdf_url,
                "waiting",
                data.telegram_user_id or ""
            ])
        except Exception as e:
            logger.error(f"Google Sheets append error: {e}")

        # Уведомление в Telegram
        if data.telegram_user_id:
            try:
                bot.send_message(
                    chat_id=data.telegram_user_id,
                    text=(f"Ваш заказ {order_id} принят. "
                          f"PDF будет доступен после оплаты.\n"
                          f"Сгенерированные изображения: {', '.join(generated_image_urls)}")
                )
            except Exception as e:
                logger.error(f"Telegram notification error: {e}")

        return JSONResponse({
            "order_id": order_id,
            "pdf_url": pdf_url,
            "user_image_url": user_image_url,
            "generated_image_urls": generated_image_urls,
            "status": "created"
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in /order: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# --- (СТАРЫЙ ВАРИАНТ ДЛЯ ВАШЕГО СЕКРЕТА, НЕ ОБЯЗАТЕЛЬНО ---
@app.post("/payment-confirm")
async def payment_confirm(
    req: Request,
    x_upak_signature: str = Header(...)
):
    if x_upak_signature != WEBHOOK_SECRET:
        logger.warning("Unauthorized payment-confirm attempt")
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        body = await req.json()
        order_id = body.get("metadata", {}).get("order_id")
        if body.get("status") == "succeeded" and order_id:
            cell = sheet.find(order_id)
            sheet.update_cell(cell.row, 10, "paid")
            sheet.update_cell(cell.row, 11, "completed")
            row = sheet.row_values(cell.row)
            pdf_url = row[9]
            telegram_id = int(row[8]) if row[8].isdigit() else None
            if telegram_id:
                try:
                    bot.send_message(
                        chat_id=telegram_id,
                        text=f"Ваш заказ {order_id} готов!\n{pdf_url}"
                    )
                except Exception as e:
                    logger.error(f"Telegram payment notification error: {e}")
        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in payment-confirm: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
