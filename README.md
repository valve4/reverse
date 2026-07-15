# Reverse — Flight Fare Finder

A Chrome extension that finds cheaper flights by searching **every** route permutation and sorting by price.

## What it does

Given **New York → London** on July 20–27, Reverse checks:

| Search type | Example |
|---|---|
| Direct outbound | JFK → LHR |
| Direct reverse | LHR → JFK (often cheaper!) |
| Nearby airports | BOS → LGW, EWR → LHR, etc |
| Split-leg | NYC → BOS → LGW (two separate bookings) |

All results render sorted by price so you always see the cheapest option first.

## Setup

### 1. Get an API key

Sign up at [Amadeus for Developers](https://developers.amadeus.com/) (free tier = 1500 req/day) for real flight data. Skyscanner is an alternate.

### 2. Install locally

1. Open Chrome → `chrome://extensions/`
2. Enable **Developer mode** (top-right)
3. Click **Load unpacked**
4. Point to this repo's root

### 3. Configure

Click the Reverse icon → the popup will have a gear or link to options. Set:

- Your API key
- Email address (for $50+ drop alerts)
- Background search schedule

## Project structure

```
reverse/
├── manifest.json          # Extension manifest (V3)
├── popup/                 # Extension popup UI
│   ├── popup.html
│   ├── popup.js
│   └── popup.css
├── options/               # Settings page
│   ├── options.html
│   ├── options.js
│   └── options.css
├── background/            # Service worker core
│   ├── background.js      # Service worker entry
│   ├── fare-search.js     # Permutation engine
│   ├── api-service.js     # Flight API integration
│   └── notifications.js # Desktop + email alerts
├── lib/                   # Shared utilities
│   └── city-data.js       # airport/city reference data
├── icons/                 # Extension icons
├── PRD.md                 # Product requirements
└── README.md
```

## Dev

```bash
# Test in Chrome
# 1. chrome://extensions/
# 2. Load unpacked → point to this repo
# 3. Refresh extension on changes
```

## License

Private — for our co-op use only.
