/**
 * background/fare-search.js — Core permutation engine
 *
 * Given origin, destination, and travel dates, generate
 * all route permutations to search:
 *  - direct outbound (A->B)
 *  - direct reverse (B->A)
 *  - nearby airports for both
 *  - split-leg combos
 */

/**
 * Generate all route queries to search.
 *
 * @param {{
 *   origin: string,
 *   destination: string,
 *   depart: string,
 *   return: string,
 *   includeReverse: boolean,
 *   includeSplit: boolean
 * }} params
 * @returns {Array<Query>}
 */
function generateQueries(params) {
  var originCity = params.origin.toLowerCase().trim();
  var destCity = params.destination.toLowerCase().trim();
  var includeReverse = params.includeReverse !== false;
  var includeSplit = params.includeSplit !== false;

  var originData = getCityData(originCity);
  var destData = getCityData(destCity);

  // Combine main airports + nearby from both sides
  var originEndpoints = originData.airports.concat(originData.nearbyWithin50mi);
  var destEndpoints = destData.airports.concat(destData.nearbyWithin50mi);

  // Ensure we always have something to search
  if (originEndpoints.length === 0) {
    originEndpoints = [{ iata: '???', name: originCity, isCity: true }];
  }
  if (destEndpoints.length === 0) {
    destEndpoints = [{ iata: '???', name: destCity, isCity: true }];
  }

  var queries = [];

  // Deduplicate by route pair
  var seen = new Set();

  /**
   * Helper to deduplicate a route key.
   * @param {string} a
   * @param {string} b
   * @returns {string}
   */
  function routeKey(a, b) {
    return a + '→' + b;
  }

  /**
   * Add a query if not already seen.
   * @param {Query} q
   */
  function addQuery(q) {
    var key = routeKey(q.originCode, q.destinationCode);
    if (!seen.has(key)) {
      seen.add(key);
      queries.push(q);
    }
  }

  // 1. Direct outbound: origin → dest (main airports)
  originEndpoints.forEach(function (orig) {
    destEndpoints.forEach(function (dest) {
      addQuery({
        originCode: orig.iata,
        destinationCode: dest.iata,
        originName: orig.name,
        destinationName: dest.name,
        depart: params.depart,
        return: params.return,
        type: 'direct',
        tags: [],
      });
    });
  });

  // 2. Direct reverse: dest → origin (often cheaper!)
  if (includeReverse) {
    destEndpoints.forEach(function (dest) {
      originEndpoints.forEach(function (orig) {
        addQuery({
          originCode: dest.iata,
          destinationCode: orig.iata,
          originName: dest.name,
          destinationName: orig.name,
          depart: params.depart,
          return: params.return,
          type: 'reverse',
          tags: ['reverse'],
        });
      });
    });
  }

  // 3. Split-leg: origin → hub → dest (each leg as separate query)
  if (includeSplit) {
    // Pick a "hub" airport near the destination to fly through
    var majorHubs = ['JFK', 'LHR', 'CDG', 'AMS', 'FRA', 'DXB', 'GRU', 'NRT'];
    majorHubs.forEach(function (hub) {
      // Try via hub from origin side
      originEndpoints.forEach(function (orig) {
        // Don't duplicate if hub is already in endpoints
        if (destEndpoints.some(function (d) { return d.iata === hub; })) return;

        addQuery({
          originCode: orig.iata,
          destinationCode: hub,
          originName: orig.name,
          destinationName: getAirportName(hub) + ' (via)',
          depart: params.depart,
          return: params.return,
          type: 'split-leg',
          subLeg: 'first',
          isVia: hub,
          tags: ['split'],
        });

        addQuery({
          originCode: hub,
          destinationCode: destEndpoints[0].iata,
          originName: getAirportName(hub) + ' (via)',
          destinationName: destEndpoints[0].name,
          depart: new Date(params.depart).getTime() + 5 * 86400000, // +5 days
          return: params.return,
          type: 'split-leg',
          subLeg: 'second',
          isVia: hub,
          tags: ['split'],
        });
      });
    });
  }

  // 4. Cross-search: origin airport → nearby dest (or vice versa)
  originEndpoints.forEach(function (orig) {
    destData.nearbyWithin50mi.forEach(function (nearby) {
      addQuery({
        originCode: orig.iata,
        destinationCode: nearby.iata,
        originName: orig.name,
        destinationName: nearby.name,
        depart: params.depart,
        return: params.return,
        type: 'nearby',
        tags: ['nearby-airport'],
      });
    });
  });

  destEndpoints.forEach(function (dest) {
    originData.nearbyWithin50mi.forEach(function (nearby) {
      addQuery({
        originCode: nearby.iata,
        destinationCode: dest.iata,
        originName: nearby.name,
        destinationName: dest.name,
        depart: params.depart,
        return: params.return,
        type: 'nearby',
        tags: ['nearby-airport'],
      });
    });
  });

  return queries;
}

/**
 * Query object shape:
 * {
 *   originCode: string,
 *   destinationCode: string,
 *   originName: string,
 *   destinationName: string,
 *   depart: string,
 *   return: string,
 *   type: 'direct' | 'reverse' | 'split-leg' | 'nearby',
 *   tags: Array<string>,
 *   isVia?: string,
 *   subLeg?: string
 * }
 */

/**
 * Group split-leg queries by via hub and match them.
 *
 * @param {Array<Query>} queries
 * @returns {Array<{originCode: string, destinationCode: string, originName: string, destinationName: string, depart: string, return: string, type: string, tags: Array<string>, via: string, totalTravelTime?: number, totalPrice?: number, stops?: number, bookingUrl?: string}>}
 */
function groupSplitLegs(queries) {
  var splitQueries = queries.filter(function (q) {
    return q.type === 'split-leg' && q.isVia;
  });

  var byHub = {};
  splitQueries.forEach(function (q) {
    if (!byHub[q.isVia]) byHub[q.isVia] = {};
    byHub[q.isVia][q.subLeg] = q;
  });

  var matched = [];
  Object.keys(byHub).forEach(function (hub) {
    var first = byHub[hub].first;
    var second = byHub[hub].second;
    if (first && second) {
      matched.push({
        originCode: first.originCode,
        destinationCode: second.destinationCode,
        originName: first.originName,
        destinationName: second.destinationName,
        depart: first.depart,
        return: second.return,
        type: 'split-leg',
        tags: ['split'],
        via: hub,
      });
    }
  });

  return matched;
}

export { generateQueries, groupSplitLegs };
