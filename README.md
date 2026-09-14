# Gas Finder WhatsApp Bot

A backend project built with Python and FastAPI that helps users find nearby gas stations, compare available fuel prices, and identify the best option based on distance and estimated travel cost.

The long-term goal is to connect this REST API to a WhatsApp bot so users can share their location and receive nearby fuel options directly in WhatsApp.

## Current Features

- Search nearby gas stations using latitude and longitude
- Retrieve gas station names, addresses, and coordinates
- Calculate approximate distance in miles
- Retrieve available fuel prices from Google Places
- Support:
  - Regular
  - Premium
  - Diesel
- Sort results by:
  - Distance
  - Price
  - Best estimated option
- Handle stations without fuel prices
- Validate query parameters
- Handle Google Places errors and timeouts
- Automated tests with pytest
- Interactive API documentation with Swagger

## Technologies

- Python
- FastAPI
- Uvicorn
- Pydantic
- HTTPX
- Google Places API (New)
- python-dotenv
- pytest
- Git
- GitHub

## Project Structure

```text
gas-finder-whatsapp-bot/
├── app/
│   ├── config.py
│   ├── main.py
│   ├── schemas.py
│   ├── services/
│   └── utils/
├── docs/
│   ├── API_USAGE.md
│   └── GOOGLE_PLACES_SETUP.md
├── tests/
├── .env.example
├── .gitignore
├── README.md
└── requirements.txt
```

## Installation

Clone the repository:

```bash
git clone https://github.com/racolinadevelop/gas-finder-whatsapp-bot.git
```

Enter the project directory:

```bash
cd gas-finder-whatsapp-bot
```

Create a virtual environment:

```bash
python3 -m venv .venv
```

Activate it on macOS or Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Environment Configuration

Create your local environment file:

```bash
cp .env.example .env
```

Then add your Google Maps API key:

```env
GOOGLE_MAPS_API_KEY=YOUR_REAL_API_KEY
```

Never commit your `.env` file.

For full Google Cloud configuration instructions, see:

[Google Places Setup](docs/GOOGLE_PLACES_SETUP.md)

## Run the API

Start the FastAPI development server:

```bash
uvicorn app.main:app --reload
```

Open Swagger:

```text
http://127.0.0.1:8000/docs
```

## Main Endpoint

```http
GET /api/v1/gas-stations/nearby
```

Main parameters include:

```text
latitude
longitude
radius
fuel_type
sort
limit
gallons_needed
vehicle_mpg
```

For complete API documentation, examples, validation rules, and error responses, see:

[API Usage Guide](docs/API_USAGE.md)

## Sorting Options

### Distance

Returns the closest stations first.

### Price

Returns the stations with the lowest available fuel price first.

Stations without price information are placed at the end.

### Best

Estimates the total cost of choosing each gas station using:

- fuel price
- distance
- round-trip travel
- gallons needed
- vehicle MPG

This helps avoid recommending a station that is slightly cheaper but much farther away.

## Testing

Run the automated test suite with:

```bash
python -m pytest -v
```

The test suite covers validation, empty results, Google Places failures, price sorting, distance sorting, and best-option logic.

## Important Limitation

The current MVP calculates distance using geographic coordinates.

This is straight-line distance, not actual driving distance.

A future version may integrate a routing service for more accurate travel calculations.

## Roadmap

Planned features include:

- WhatsApp Cloud API integration
- WhatsApp location sharing
- User commands for fuel type and sorting
- PostgreSQL database
- Search history
- Favorite gas stations
- Price alerts
- Actual driving distance
- Docker
- Production deployment

## Security

Never commit:

- `.env`
- API keys
- passwords
- private credentials

API keys should be stored using environment variables and restricted in Google Cloud.

## Status

Project currently in active development.