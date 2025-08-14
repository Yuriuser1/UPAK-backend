# UPAK Backend FastAPI MVP

FastAPI-based backend for the UPAK marketplace automation platform.

## Features

- **FastAPI Framework**: High-performance async web framework
- **Payment Processing**: YooKassa integration with webhook support
- **AI Text Generation**: Yandex GPT for product descriptions
- **Image Processing**: DALL-E image generation and background removal
- **File Storage**: Firebase Cloud Storage integration
- **Data Management**: Google Sheets integration for order tracking
- **Notifications**: Telegram bot integration
- **PDF Generation**: Automated PDF reports with ReportLab

## API Endpoints

- `POST /create_payment` - Create payment via YooKassa
- `POST /yookassa-webhook` - Handle payment webhooks
- `POST /order` - Create new product order
- `POST /payment-confirm` - Alternative payment confirmation

## Environment Setup

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Configure your environment variables:
   - Telegram Bot Token
   - Yandex GPT API credentials
   - OpenAI API key (for DALL-E)
   - YooKassa credentials
   - Firebase credentials
   - Google Sheets credentials

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Place credential files:
   - `firebase_credentials.json` (Firebase service account)
   - `credentials.json` (Google Sheets service account)

## Running the Application

Development mode:
```bash
uvicorn main:app --reload --port 8000
```

Production mode:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Docker Support

Build and run with Docker:
```bash
docker build -t upak-backend .
docker run -p 8000:8000 upak-backend
```

## Contributing

This is an MVP version. For production deployment, ensure all security credentials are properly configured and stored securely.
