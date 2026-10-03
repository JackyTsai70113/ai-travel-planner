# Flight and hotel search providers

## Flights

Production planning does not call an airfare API. It does not scrape or automate Google Flights. Canonical Trip contains a `flight_search_url` to the public Google Flights search page and a separate route/date summary to enter there. Google does not document a public URL format for prefilled flight searches, and a free-text query link redirected to an unsupported page during browser verification, so the link opens the working search page without pretending to prefill it. Prices shown on Google Flights are external, can change, and are not returned as repository candidates or included in the trip budget.

Google's Flights Search integration is a partner-only program. The public Google Flights website can be opened by users without a repository API key.

## Hotels

The current production adapter still uses Amadeus Self-Service hotel search when both `AMADEUS_CLIENT_ID` and `AMADEUS_CLIENT_SECRET` are supplied. Those credentials are optional for planning; without them the trip can be planned without hotel candidates and the research stage records that hotel search is unavailable. Amadeus's Self-Service portal was retired; do not expect new credentials from the old registration flow. A replacement hotel provider has not been configured.

Hotel adapter results, when available from an existing compatible account, remain unverified search quotes and do not make reservations. Do not configure paid or Enterprise credentials until their API and endpoint compatibility has been confirmed.

## Other production credentials

The following remain required by `src.application.production`: `GOOGLE_MAPS_API_KEY` for Places research, `YOUTUBE_API_KEY` for community video evidence, and `OPENROUTESERVICE_API_KEY` for driving/walking route matrices. Keep provider keys in the backend's secret environment and restrict them in each provider console.

### OpenRouteService key

1. Create or sign in to an account at [OpenRouteService / HeiGIT](https://openrouteservice.org/log-in/). The sign-in page links to the account used to access the developer dashboard.
2. In the developer dashboard, create a Standard API key. The Standard plan is listed at €0 and has request quotas; this project uses the Matrix endpoint, whose published Standard quota is 500 requests per day and 40 per minute. Review the current [plan limits](https://openrouteservice.org/plans/) and [endpoint restrictions](https://openrouteservice.org/restrictions/) before production use.
3. Copy the generated key and add it to the Railway production service as the secret variable `OPENROUTESERVICE_API_KEY`. Do not add it to GitHub Actions, the repository, source code, or an MCP tool argument. No payment details are needed for the free Standard plan; exceeding its quotas causes API errors and repeated excessive use can result in a temporary block.
4. The Matrix adapter uses the current endpoint `https://api.heigit.org/openrouteservice/v2/matrix`. Existing keys are valid on the new HeiGIT host. Do not use the deprecated `api.openrouteservice.org` host: its shutdown is scheduled for November 2–6, 2026.
5. After Railway deploys the new secret, use a small planning request or a direct Matrix API smoke check to confirm that the key is accepted. Avoid printing the key in shell history or logs.
