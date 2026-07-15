# PRD: Reverse — Reverse-Direction Flight Fare Finder

## 1. Problem

Flyers often look for flights **in the wrong direction** because they assume "outbound" searches (e.g. NYC → London) are the cheapest option. In reality, **return-direction** fares (London → NYC) on the same calendar days are frequently **significantly cheaper** — same plane, just flipped.

Most people don't think to search it that way, and most flight sites don't make it easy to compare.

**Reverse** solves this.

## 2. Product

A Chrome extension that:
- Searches flight prices across **multiple route permutations** for the same travel dates
- Surfaces the cheapest options
- Notifies the user of deals above a threshold

### What it does (MVP)

| Feature | Detail |
|---|---|
| **Input** | User picks: origin city, destination city, travel dates |
| **Search logic** | For NYC → London on July 20–27, also checks: |
| | &nbsp;&nbsp;• Reverse direction: **London → NYC** |
| | &nbsp;&nbsp;• Split-leg: NYC → BOS, BOS → London (etc.) |
| | &nbsp;&nbsp;• Nearby airports: JFK, LGA, EWR, BOS |
| | &nbsp;&nbsp;• Combined reverse + airport: LHR → EWR + JFK → NYC |
| **Output** | All options shown in the extension popup, sorted by total price low → high |
| **Trigger** | Two modes: (a) Manual click, (b) Background schedule (configurable) |
| **Notification** | Popup on new finds; email to the user's provided address when a fare drops ≥ $50 vs. the previous search |

### Scope (out of MVP)

- Booking the flight (future phase)
- Saving/favoriting routes
- Price alerts for a specific route
- Multi-passenger support
- Mobile app

## 3. User Workflow

```
1. User clicks Reverse icon in Chrome toolbar
2. Popup shows a search form:
       Origin City: [new york]
       Destination: [london]
       Depart: [Jul 20] → Return: [Jul 27]
       [Search] button
3. User clicks Search → extension runs all permutations in the background
4. Results render in the popup sorted by price:
       Best option: London LHR → NYC EWR via BOS — $312
         Reverse-direction, split-leg, cheapest by $87
       Option 2: NYC JFK → London LHR direct — $399
       Option 3: ...
5. If any new option is ≥ $50 cheaper than the last search:
       User gets a desktop notification + email
```

## 4. Technical Architecture

### Chrome Extension Structure
```
reverse/
├── manifest.json            # Manifest V3
├── popup/
│   ├── popup.html           # Search form + results list
│   ├── popup.js
│   └── popup.css
├── content/
│   └── (minimal — mostly background work)
├── background/
│   ├── service-worker.js    # Handles scheduled background searches
│   └── fare-search.js       # Core search logic (permutations + API)
├── options/
│   ├── options.html         # Settings page
│   ├── options.js
│   └── options.css
├── lib/
│   └── api.js               # Skyscanner/Kayak API wrapper
└── assets/
    └── icons/
```

### API Choice
- **Skyscanner API** (free tier) or **Kiwi.com Skyscanner aggregator** — we'll evaluate both for free-tier availability and rate limits
- Fallback: **Amadeus API** (generous free tier for development)

### Permutation Engine

```
Given: origin = ["JFK", "LGA", "EWR", "BOS"], destination = ["LHR", "LGW"]
Travel dates: 2026-07-20 / 2026-07-27

Permutations to check (all at once):
1. JFK → LHR  (direct, standard outbound)
2. JFK → LGW
3. LGA → LHR
4. LGA → LGW
5. EWR → LHR
6. EWR → LGW
7. BOS → LHR
8. BOS → LGW
9. LHR → JFK  (REVERSE — often cheapest)
10. LGW → JFK
11. LHR → LGA
12. LGW → LGA
13. ... + split-leg variants (origin→hub→destination on separate bookings)
```

### Background Schedule
- User-configurable: daily / weekly / disabled
- Runs at a random time (to avoid API rate limits)
- Stores results in `chrome.storage.local`
- Comparison logic: if cheapest_fare < previous_cheapest_fare - $50 → notify

### Notifications
- Desktop: `chrome.notifications.create()`
- Email: via simple email service (e.g. Resend API or Mailgun free tier)
- Email configurable in extension options

## 5. Settings Page (Options)

| Setting | Default |
|---|---|
| Email address | (empty — required before first email) |
| Background search frequency | Disabled |
| Email threshold | $50 |
| Max concurrent searchers | 5 |
| Currency preference | USD |

## 6. Non-Goals (MVP)

- No login/signup
- No payment processing
- No saved searches
- No mobile support
- No actual booking (just link to the airline or travel site)

## 7. Success Criteria (MVP)

- [ ] Extension installs and shows popup form
- [ ] User can input origin/destination/dates
- [ ] All permutations search and return results
- [ ] Results render sorted by price in popup
- [ ] Manual search works
- [ ] Background search runs on schedule
- [ ] $50+ drops trigger notification + email
- [ ] Works with Skyscanner/Amadeus free API

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Flight API has no truly free tier | Start with Amadeus free tier (1500 req/day); if needed, mock data for development |
| Chrome extension rate limits | Background searches throttle to ~1 req/sec; random jitter on schedule |
| "Reverse flights" aren't always cheaper | Show every option — no filtering; let the user decide |
| Split-leg is complex (two separate bookings) | Label clearly: "requires 2 bookings" |

## 9. Tech Stack

- **Extension**: Manifest V3 Chrome extension (vanilla JS, no framework for MVP)
- **Storage**: `chrome.storage.local`
- **API**: Amadeus or Skyscanner API
- **Styling**: Plain CSS (Tailwind or similar deferred to v2 if needed)

## 10. Future Phases

1. **Save favorites** — persist best routes locally
2. **Price history** — show trend lines over time
3. **Multi-passenger** — search for 2+ travelers
4. **Booking integration** — deep-link to actual booking
5. **Public launch** — website, documentation, distribution

---

**Author**: Wesley + Claude  
**Date**: 2026-07-14  
**Status**: Draft PRD — ready to review
