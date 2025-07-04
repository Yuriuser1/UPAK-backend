```python
from fastapi import FastAPI, Request, Header, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import openai, io, base64, os, logging
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

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация приложения
app = FastAPI()

# Настройки OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Телеграм-бот
bot = telegram.Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
chat_id_template = os.getenv("TELEGRAM_CHAT_ID_TEMPLATE")

# Безопасный секрет для вебхуков
WEBHOOK_SECRET = os.getenv("PAYMENT_WEBHOOK_SECRET")

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

# Модель запроса
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

        # Генерация текста через OpenAI
        messages = [
            {"role": "system", "content": "Вы создаёте карточку для WB/Ozon."},
            {"role": "user", "content": (
                f"Товар: {data.product_name}. "
                f"Характеристики: {data.product_features}."
            )}
        ]
        try:
            res = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=600
            )
            content = res.choices[0].message.content.strip()
            title, description = content.split("\n", 1)
        except Exception as e:
            logger.error(f"OpenAI text generation error: {e}")
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
                "waiting"
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

@app.post("/payment-confirm")
async def payment_confirm(
    req: Request,
    x_upak_signature: str = Header(...)
):
    # Проверка секрета
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
```
