/**
 * background/api-service.js — Flight API integration layer
 *
 * Handles authentication with Amadeus/Skyscanner API,
 * rate limiting, retry logic, and response parsing.
 */

/**
 * Fetches flight fares for a single query.
 * Currently uses mock data for development since real APIs
 * require valid credentials from the user's settings.
 *
 * @param {Query} query
 * @param {object} settings
 * @returns {Promise<Fare>}
 */
async function fetchFare(query, settings) {
  var provider = settings.apiProvider || 'amadeus';

  // If real API keys are configured, use them
  if (provider === 'amadeus' && settings.apiKey && settings.apiSecret) {
    return fetchViaAmadeus(query, settings);
  }

  // If no valid API key, return mock data for development
  console.warn('[fare-search] No valid API keys configured. Using mock data for dev.');
  return generateMockFare(query);
}

/**
 * Fetch real fares via Amadeus API.
 *
 * @param {Query} query
 * @param {object} settings
 * @returns {Promise<Fare>}
 */
async function fetchViaAmadeus(query, settings) {
  // Step 1: Get OAuth token
  var token = await getAmadeusToken(settings);

  // Step 2: Search low-fare dates
  var url = 'https://test.api.amadeus.com/v2/shopping/flight-offers';
  var params = new URLSearchParams();
  params.set('originLocationCode', query.originCode);
  params.set('destinationLocationCode', query.destinationCode);
  params.set('departureDate', formatDateForAPI(query.depart));
  params.set('returnDate', formatDateForAPI(query.return));
  params.set('adults', '1');
  params.set('max', '1');
  params.set('currencyCode', 'USD');

  var response = await fetch(url + '?' + params.toString(), {
    method: 'GET',
    headers: {
      'Authorization': 'Bearer ' + token,
      'Accept': 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error('Amadeus API error: ' + response.status);
  }

  var data = await response.json();

  // Parse the first result into our Fare shape
  if (data.data && data.data.length > 0) {
    var result = data.data[0];
    return parseAmadeusResult(result, query);
  }

  return null;
}

/**
 * Get or refresh Amadeus OAuth token.
 * Uses chrome.storage.local to cache the token.
 *
 * @param {object} settings
 * @returns {Promise<string>}
 */
var _cachedToken = null;
var _tokenExpiry = 0;

async function getAmadeusToken(settings) {
  var now = Date.now();
  if (_cachedToken && now < _tokenExpiry) {
    return _cachedToken;
  }

  var cached = await chrome.storage.local.get('amadeusToken');
  if (cached.amadeusToken && cached.tokenExpiry && now < cached.tokenExpiry) {
    _cachedToken = cached.amadeusToken;
    _tokenExpiry = cached.tokenExpiry;
    return _cachedToken;
  }

  // Request new token from Amadeus
  var authUrl = 'https://secure.amadeus.com/api-security/token';
  var authResponse = await fetch(authUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'Authorization': 'Basic ' + btoa(settings.apiKey + ':' + settings.apiSecret),
    },
    body: 'grant_type=client_credentials',
  });

  if (!authResponse.ok) {
    throw new Error('Amadeus auth error: ' + authResponse.status);
  }

  var authData = await authResponse.json();
  _cachedToken = authData.access_token;
  _tokenExpiry = now + (authData.expires_in * 1000);

  // Cache in chrome.storage
  await chrome.storage.local.set({
    amadeusToken: _cachedToken,
    tokenExpiry: _tokenExpiry,
  });

  return _cachedToken;
}

/**
 * Parse Amadeus API response into our Fare shape.
 *
 * @param {object} result — single flight-offer object from Amadeus
 * @param {Query} query
 * @returns {Fare}
 */
function parseAmadeusResult(result, query) {
  var price = result.price?.total || 0;
  var itineraries = result.itineraries || [];
  var totalTravelTime = 0;
  var stops = 0;

  // Calculate travel time from first itinerary
  if (itineraries.length > 0) {
    var first = itineraries[0];
    var segments = first.segments || [];
    if (segments.length > 0) {
      var depTime = new Date(segments[0].departure);
      var arrTime = new Date(segments[segments.length - 1].arrival);
      totalTravelTime = arrTime - depTime;
      stops = segments.length - 1;
    }
  }

  // Build booking URL (Amadeus doesn't always provide one, we'd construct from airline info)
  var bookingUrl = '';

  return {
    originCode: query.originCode,
    destinationCode: query.destinationCode,
    totalPrice: price,
    totalTravelTime: totalTravelTime,
    stops: Math.max(0, stops),
    tags: query.tags || [],
    bookingUrl: bookingUrl,
  };
}

/**
 * Generate a realistic mock fare for development use.
 * Real data comes from the API once the user adds their key.
 *
 * @param {Query} query
 * @returns {Fare}
 */
function generateMockFare(query) {
  var basePrice = 300;

  // Adjust price by type to simulate realistic pricing
  if (query.type === 'reverse') {
    basePrice = 280 + Math.floor(Math.random() * 80); // Often cheaper
  } else if (query.type === 'split-leg') {
    basePrice = 250 + Math.floor(Math.random() * 120); // Can go either way
  } else if (query.type === 'nearby') {
    basePrice = 310 + Math.floor(Math.random() * 100);
  } else {
    basePrice = 350 + Math.floor(Math.random() * 150); // Direct usually more
  }

  var totalTravelTime = 420 + Math.floor(Math.random() * 300); // in minutes

  return {
    originCode: query.originCode,
    destinationCode: query.destinationCode,
    totalPrice: basePrice,
    totalTravelTime: totalTravelTime * 60000, // convert to ms
    stops: query.type === 'split-leg' || query.type === 'reverse' ? 0 : Math.floor(Math.random() * 3),
    tags: query.tags || [],
    bookingUrl: '',
    via: query.isVia || null,
  };
}

/**
 * Format a date string to YYYY-MM-DD for API.
 *
 * @param {string} dateStr
 * @returns {string}
 */
function formatDateForAPI(dateStr) {
  if (typeof dateStr === 'number') {
    var d = new Date(dateStr);
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }
  return dateStr.substring(0, 10);
}

/**
 * Rate-limited fetch with retry logic.
 *
 * @param {function} fetchFn — async function that does the actual fetch
 * @param {object} opts
 * @param {number} [opts.maxRetries=3]
 * @param {number} [opts.initialDelay=1000]
 * @returns {Promise<*>}
 */
async function rateLimitedFetch(fetchFn, opts) {
  opts = opts || {};
  var maxRetries = opts.maxRetries || 3;
  var initialDelay = opts.initialDelay || 1000;

  for (var attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      // Rate limit: wait between requests
      if (attempt > 0) {
        var delay = initialDelay * Math.pow(2, attempt - 1);
        await sleep(delay);
      }
      return await fetchFn();
    } catch (err) {
      console.warn('[api-service] Fetch attempt ' + (attempt + 1) + ' failed:', err);
      if (attempt === maxRetries) throw err;
    }
  }
}

/**
 * Sleep utility.
 * @param {number} ms
 * @returns {Promise<void>}
 */
function sleep(ms) {
  return new Promise(function (resolve) {
    setTimeout(resolve, ms);
  });
}

export { fetchFare, rateLimitedFetch };
