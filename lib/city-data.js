/**
 * lib/city-data.js — Airport/city reference data
 * Maps city names to their airports and airport codes.
 */

var CITY_DATA = {
  'new york': {
    airports: [
      { iata: 'JFK', name: 'John F. Kennedy International', city: 'New York' },
      { iata: 'LGA', name: 'LaGuardia Airport', city: 'New York' },
      { iata: 'EWR', name: 'Newark Liberty International', city: 'Newark' },
    ],
    nearbyWithin50mi: [
      { iata: 'HPN', name: 'Westchester County', city: 'Purchase, NY' },
      { iata: 'ISP', name: 'Long Island MacArthur', city: 'Islip, NY' },
      { iata: 'BDR', name: 'Bradley International', city: 'Stamford, CT' },
    ],
  },
  'london': {
    airports: [
      { iata: 'LHR', name: 'Heathrow', city: 'London' },
      { iata: 'LGW', name: 'Gatwick', city: 'London' },
      { iata: 'STN', name: 'Stansted', city: 'London' },
      { iata: 'LTN', name: 'Luton', city: 'London' },
      { iata: 'LCY', name: 'City Airport', city: 'London' },
      { iata: 'SEN', name: 'Southend', city: 'London' },
    ],
    nearbyWithin50mi: [
      { iata: 'OXF', name: 'Oxford (Cotswold)', city: 'Oxfordshire' },
      { iata: 'CBG', name: 'Cambridge', city: 'Cambridge' },
      { iata: 'BRS', name: 'Bristol', city: 'Bristol' },
    ],
  },
  'los angeles': {
    airports: [
      { iata: 'LAX', name: 'Los Angeles International', city: 'Los Angeles' },
      { iata: 'BUR', name: 'Hollywood Burbank', city: 'Burbank' },
      { iata: 'LGB', name: 'Long Beach', city: 'Long Beach' },
      { iata: 'SNA', name: 'John Wayne Airport', city: 'Santa Ana' },
    ],
    nearbyWithin50mi: [
      { iata: 'PMD', name: 'Palmdale', city: 'Palmdale' },
      { iata: 'ONT', name: 'Ontario International', city: 'Ontario' },
    ],
  },
  'paris': {
    airports: [
      { iata: 'CDG', name: 'Charles de Gaulle', city: 'Paris' },
      { iata: 'ORY', name: 'Orly', city: 'Paris' },
      { iata: 'BVA', name: 'Beauvais-Tillé', city: 'Beauvais' },
    ],
    nearbyWithin50mi: [
      { iata: 'LBG', name: 'Paris-Le Bourget', city: 'Le Bourget' },
      { iata: 'XCR', name: 'Chalons-Vatry', city: 'Chalons' },
    ],
  },
  'tokyo': {
    airports: [
      { iata: 'NRT', name: 'Narita International', city: 'Tokyo' },
      { iata: 'HND', name: 'Haneda Airport', city: 'Tokyo' },
    ],
    nearbyWithin50mi: [
      { iata: 'IJX', name: 'Ishigaki', city: 'Ishigaki' },
    ],
  },
  'chicago': {
    airports: [
      { iata: 'ORD', name: "O'Hare International", city: 'Chicago' },
      { iata: 'MDW', name: 'Midway International', city: 'Chicago' },
    ],
    nearbyWithin50mi: [
      { iata: 'GYY', name: 'Gary/Chicago International', city: 'Gary, IN' },
      { iata: 'PWK', name: 'Chicago Executive', city: 'Wheeling, IL' },
    ],
  },
  'san francisco': {
    airports: [
      { iata: 'SFO', name: 'San Francisco International', city: 'San Francisco' },
      { iata: 'OAK', name: 'Oakland International', city: 'Oakland' },
      { iata: 'SJC', name: 'Norman Y. Mineta San Jose', city: 'San Jose' },
    ],
    nearbyWithin50mi: [
      { iata: 'PAO', name: 'Palo Alto', city: 'Palo Alto' },
    ],
  },
  'miami': {
    airports: [
      { iata: 'MIA', name: 'Miami International', city: 'Miami' },
      { iata: 'FLL', name: 'Fort Lauderdale–Hollywood', city: 'Fort Lauderdale' },
      { iata: 'PBI', name: 'West Palm Beach', city: 'West Palm Beach' },
    ],
    nearbyWithin50mi: [],
  },
  'dallas': {
    airports: [
      { iata: 'DFW', name: "Dallas/Fort Worth International", city: 'Dallas' },
      { iata: 'DAL', name: 'Dallas Love Field', city: 'Dallas' },
    ],
    nearbyWithin50mi: [],
  },
  'seattle': {
    airports: [
      { iata: 'SEA', name: 'Seattle-Tacoma International', city: 'Seattle' },
    ],
    nearbyWithin50mi: [
      { iata: 'PDX', name: 'Portland International', city: 'Portland, OR' },
      { iata: 'BFI', name: 'Boeing Field', city: 'Seattle' },
    ],
  },
  'boston': {
    airports: [
      { iata: 'BOS', name: 'Logan International', city: 'Boston' },
    ],
    nearbyWithin50mi: [
      { iata: 'MHT', name: 'Manchester-Boston Regional', city: 'Manchester, NH' },
      { iata: 'PVD', name: 'T.F. Green', city: 'Providence, RI' },
    ],
  },
  'portland': {
    airports: [
      { iata: 'PDX', name: 'Portland International', city: 'Portland' },
    ],
    nearbyWithin50mi: [],
  },
  'denver': {
    airports: [
      { iata: 'DEN', name: 'Denver International', city: 'Denver' },
    ],
    nearbyWithin50mi: [],
  },
  'washington': {
    airports: [
      { iata: 'DCA', name: 'Ronald Reagan Washington National', city: 'Washington DC' },
      { iata: 'IAD', name: 'Washington Dulles International', city: 'Washington DC' },
      { iata: 'BWI', name: 'Baltimore/Washington International', city: 'Baltimore' },
    ],
    nearbyWithin50mi: [],
  },
  'detroit': {
    airports: [
      { iata: 'DTW', name: 'Detroit Metropolitan Wayne County', city: 'Detroit' },
    ],
    nearbyWithin50mi: [
      { iata: 'YVR', name: 'Vancouver International', city: 'Vancouver, Canada' },
    ],
  },
  'atlanta': {
    airports: [
      { iata: 'ATL', name: 'Hartsfield–Jackson Atlanta International', city: 'Atlanta' },
    ],
    nearbyWithin50mi: [
      { iata: 'MGM', name: 'Middle Georgia Regional', city: 'Macon, GA' },
    ],
  },
  'houston': {
    airports: [
      { iata: 'IAH', name: 'George Bush Intercontinental', city: 'Houston' },
      { iata: 'HOU', name: 'William P. Hobby', city: 'Houston' },
    ],
    nearbyWithin50mi: [],
  },
  'las vegas': {
    airports: [
      { iata: 'LAS', name: 'Harry Reid International', city: 'Las Vegas' },
    ],
    nearbyWithin50mi: [
      { iata: 'PHX', name: 'Phoenix Sky Harbor', city: 'Phoenix, AZ' },
    ],
  },
  'philadelphia': {
    airports: [
      { iata: 'PHL', name: 'Philadelphia International', city: 'Philadelphia' },
    ],
    nearbyWithin50mi: [
      { iata: 'ABE', name: 'Lehigh Valley International', city: 'Allentown, PA' },
      { iata: 'TTN', name: 'Trenton–Mercer', city: 'Trenton, NJ' },
    ],
  },
  'dublin': {
    airports: [
      { iata: 'DUB', name: 'Dublin Airport', city: 'Dublin' },
    ],
    nearbyWithin50mi: [
      { iata: 'SOU', name: 'Southampton', city: 'Southampton, UK' },
      { iata: 'BHX', name: 'Birmingham', city: 'Birmingham, UK' },
    ],
  },
  'berlin': {
    airports: [
      { iata: 'BER', name: 'Berlin Brandenburg', city: 'Berlin' },
    ],
    nearbyWithin50mi: [],
  },
  'amsterdam': {
    airports: [
      { iata: 'AMS', name: 'Amsterdam Airport Schiphol', city: 'Amsterdam' },
    ],
    nearbyWithin50mi: [
      { iata: 'RTM', name: 'Rotterdam The Hague', city: 'Rotterdam' },
      { iata: 'EIN', name: 'Eindhoven', city: 'Eindhoven' },
    ],
  },
  'rome': {
    airports: [
      { iata: 'FCO', name: 'Leonardo da Vinci–Fiumicino', city: 'Rome' },
      { iata: 'CIA', name: 'Ciampino', city: 'Rome' },
    ],
    nearbyWithin50mi: [
      { iata: 'PSA', name: 'Pisa International', city: 'Pisa' },
      { iata: 'BLQ', name: 'Bologna Guglielmo Marconi', city: 'Bologna' },
    ],
  },
  'barcelona': {
    airports: [
      { iata: 'BCN', name: 'Barcelona–El Prat', city: 'Barcelona' },
    ],
    nearbyWithin50mi: [
      { iata: 'GRO', name: 'Girona-Costa Brava', city: 'Girona' },
      { iata: 'REU', name: 'Reus', city: 'Reus' },
    ],
  },
  'madrid': {
    airports: [
      { iata: 'MAD', name: 'Adolfo Suárez Madrid–Barajas', city: 'Madrid' },
    ],
    nearbyWithin50mi: [
      { iata: 'VLC', name: 'Valencia', city: 'Valencia' },
      { iata: 'SGS', name: 'Segovia', city: 'Segovia' },
    ],
  },
  'sydney': {
    airports: [
      { iata: 'SYD', name: 'Kingsford Smith', city: 'Sydney' },
    ],
    nearbyWithin50mi: [],
  },
  'singapore': {
    airports: [
      { iata: 'SIN', name: 'Changi Airport', city: 'Singapore' },
      { iata: 'XSP', name: 'Seletar Airport', city: 'Singapore' },
    ],
    nearbyWithin50mi: [
      { iata: 'JHB', name: 'Johor Bahru Sultan Ismail', city: 'Johor Bahru, Malaysia' },
      { iata: 'BTU', name: 'Bintulu', city: 'Bintulu' },
    ],
  },
  'istanbul': {
    airports: [
      { iata: 'IST', name: 'Istanbul Airport', city: 'Istanbul' },
      { iata: 'SAW', name: 'Sabiha Gokcen International', city: 'Istanbul' },
    ],
    nearbyWithin50mi: [],
  },
  'dubai': {
    airports: [
      { iata: 'DXB', name: 'Dubai International', city: 'Dubai' },
      { iata: 'DWC', name: 'Al Maktoum International', city: 'Dubai' },
    ],
    nearbyWithin50mi: [
      { iata: 'SHJ', name: 'Sharjah International', city: 'Sharjah' },
      { iata: 'AUH', name: 'Abu Dhabi International', city: 'Abu Dhabi' },
    ],
  },
  'mumbai': {
    airports: [
      { iata: 'BOM', name: 'Chhatrapati Shivaji Maharaj International', city: 'Mumbai' },
    ],
    nearbyWithin50mi: [
      { iata: 'PNQ', name: 'Pune Airport', city: 'Pune' },
    ],
  },
  'bangkok': {
    airports: [
      { iata: 'BKK', name: 'Suvarnabhumi Airport', city: 'Bangkok' },
      { iata: 'DMK', name: 'Don Mueang International', city: 'Bangkok' },
    ],
    nearbyWithin50mi: [],
  },
  'capetown': {
    airports: [
      { iata: 'CPT', name: 'Cape Town International', city: 'Cape Town' },
    ],
    nearbyWithin50mi: [],
  },
  'reykjavik': {
    airports: [
      { iata: 'KEF', name: 'Keflavik International', city: 'Reykjavik' },
      { iata: 'RKV', name: 'Reykjavik Domestic', city: 'Reykjavik' },
    ],
    nearbyWithin50mi: [],
  },
};

// Default city data for airports not in our list
CITY_DATA['_default'] = {
  airports: [],
  nearbyWithin50mi: [],
};

/**
 * Get airport data for a city name.
 * @param {string} city
 * @returns {{airports: Array, nearbyWithin50mi: Array}}
 */
function getCityData(city) {
  var key = city.toLowerCase().trim();
  return CITY_DATA[key] || CITY_DATA['_default'];
}

/**
 * Convert an airport code to its full name.
 * @param {string} iata
 * @returns {string}
 */
function getAirportName(iata) {
  for (var key in CITY_DATA) {
    if (key === '_default') continue;
    var data = CITY_DATA[key];
    var all = data.airports.concat(data.nearbyWithin50mi);
    for (var i = 0; i < all.length; i++) {
      if (all[i].iata === iata) return all[i].name;
    }
  }
  return iata;
}
