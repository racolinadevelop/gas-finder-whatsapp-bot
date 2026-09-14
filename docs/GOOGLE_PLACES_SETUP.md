# Google Places API Setup

This project uses Google Places API (New) to find nearby gas stations and retrieve available fuel price information.

## 1. Create a Google Cloud Project

1. Go to Google Cloud Console.
2. Create a new project.
3. Give the project a name, for example:

   `Gas Finder WhatsApp Bot`

4. Select the new project.

## 2. Configure Billing

Google Maps Platform requires a billing account.

1. Open the Google Cloud Console menu.
2. Go to **Billing**.
3. Create or select a billing account.
4. Link the billing account to your project.

## 3. Enable Places API (New)

1. Go to **APIs & Services → Library**.
2. Search for `Places API (New)`.
3. Open it.
4. Click **Enable**.

## 4. Create an API Key

1. Go to **APIs & Services → Credentials**.
2. Create an API key.
3. Do not publish this key on GitHub.

## 5. Restrict the API Key

Restrict the API key so that it can only use:

`Places API (New)`

Additional application restrictions should be configured when the application is deployed to production.

## 6. Configure Environment Variables

Create a `.env` file in the root directory of the project.

Add:

```env
GOOGLE_MAPS_API_KEY=YOUR_REAL_API_KEY
```

The `.env` file must never be committed to GitHub.

This project includes an `.env.example` file containing:

```env
GOOGLE_MAPS_API_KEY=
```

You can create your local `.env` file with:

```bash
cp .env.example .env
```

Then add your own Google Maps API key.

## 7. Create a Virtual Environment

Create the Python virtual environment:

```bash
python3 -m venv .venv
```

Activate it on macOS or Linux:

```bash
source .venv/bin/activate
```

## 8. Install Dependencies

Install all project dependencies:

```bash
pip install -r requirements.txt
```

## 9. Run the API

Start the FastAPI development server:

```bash
uvicorn app.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000/docs
```

This opens the Swagger documentation.

## Security Notes

Never commit:

- `.env`
- API keys
- passwords
- private credentials

Do not place API keys directly inside Python source files.

## Troubleshooting

### Google Places authentication or permission error

Check that:

- Places API (New) is enabled.
- Billing is active.
- The API key is correct.
- The API key has access to Places API (New).

### No fuel prices available

Not every gas station has fuel price information available through Google Places.

If a price is unavailable, the application returns that fuel price as unavailable instead of treating it as an application error.