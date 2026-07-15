/**
 * background/background.js — Chrome Extension service worker entry point
 *
 * Handles:
 * - Incoming messages from popup (search requests)
 * - Background alarm scheduling (periodic searches)
 * - Message passing between popup and search results
 */

import { generateQueries, groupSplitLegs } from './fare-search.js';
import { fetchFare, rateLimitedFetch } from './api-service.js';
import { checkForBigDrops } from './notifications.js';

// ---- Message dispatch ----
chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
  if (message.action === 'search') {
    handleSearch(message.data)
      .then(function (results) {
        sendResponse(results);
      })
      .catch(function (err) {
        console.error('[background] Search error:', err);
        sendResponse({ success: false, error: err.message });
      });
    return true; // async response
  }

  if (message.action === 'updateSchedule') {
    updateAlarmSchedule(message.frequency);
    sendResponse({ success: true });
    return true;
  }
});

/**
 * Handle a search request from the popup.
 *
 * @param {{origin: string, destination: string, depart: string, return: string, includeReverse?: boolean, includeSplit?: boolean}} data
 * @returns {Promise<{success: boolean, fares: Array<Fare>}>}
 */
async function handleSearch(data) {
  // Load settings from chrome storage
  var settings = await chrome.storage.local.get({
    apiProvider: 'amadeus',
    apiKey: '',
    apiSecret: '',
    email: '',
    emailThreshold: 50,
    backgroundFrequency: 'disabled',
    currency: 'USD',
    maxResults: 20,
    includeReverse: true,
    includeSplit: true,
  });

  // Generate all queries
  var queries = generateQueries({
    origin: data.origin,
    destination: data.destination,
    depart: data.depart,
    return: data.return,
    includeReverse: data.includeReverse !== undefined ? data.includeReverse : settings.includeReverse,
    includeSplit: data.includeSplit !== undefined ? data.includeSplit : settings.includeSplit,
  });

  // Fetch fares for each query concurrently (rate limited)
  console.log('[background] Generating ' + queries.length + ' queries from ' + data.origin + '→' + data.destination);

  var results = await Promise.all(
    queries.map(async function (query) {
      try {
        var fare = await rateLimitedFetch(function () {
          return fetchFare(query, settings);
        }, { maxRetries: 2, initialDelay: 100 });
        return fare;
      } catch (err) {
        console.warn('[background] Failed to fetch fare for', query.originCode + '→' + query.destinationCode, err);
        return null;
      }
    })
  ).catch(function (err) {
    console.error('[background] Promise.all error:', err);
    return [];
  });

  // Filter nulls and sort by price ascending
  var fares = results.filter(Boolean).sort(function (a, b) {
    return a.totalPrice - b.totalPrice;
  }).slice(0, settings.maxResults || 20);

  // Load previous results for comparison
  var previous = await chrome.storage.local.get('previousFares');
  var prevFares = previous.previousFares || [];

  // Check for big drops and send notifications
  if (fares.length > 0) {
    var dropInfo = await checkForBigDrops(fares, settings, prevFares);
    if (dropInfo.bigDropFare) {
      console.log('[background] Big drop detected! Fare:' + dropInfo.bigDropFare.originCode + '→' + dropInfo.bigDropFare.destinationCode + ' — $' + dropInfo.bigDropFare.totalPrice);
    }
  }

  // Store current results for next comparison
  await chrome.storage.local.set({
    previousFares: fares.map(function (f) {
      var copy = Object.assign({}, f);
      copy.searchedAt = new Date().toISOString();
      return copy;
    }),
  });

  return { success: true, fares: fares };
}

/**
 * Set up the background alarm for scheduled searches.
 *
 * @param {string} frequency — 'disabled' | 'daily' | 'weekly' | '12hours'
 */
function updateAlarmSchedule(frequency) {
  // Clear existing alarm
  chrome.alarms.clear('reverse-background-search');

  if (frequency === 'disabled') return;

  // Get search settings from storage
  chrome.storage.local.get(['origin', 'destination', 'depart', 'return'], function (items) {
    if (items.origin && items.destination && items.depart && items.return) {
      var schedule = frequency === 'daily'
        ? { periodInMinutes: 1440 }
        : frequency === 'weekly'
          ? { periodInMinutes: 10080 }
          : frequency === '12hours'
            ? { periodInMinutes: 720 }
            : null;

      if (schedule) {
        chrome.alarms.create('reverse-background-search', schedule);
        console.log('[background] Alarm scheduled for every ' + frequency);
      }
    }
  });
}

// Handle alarm events
chrome.alarms.onAlarm.addListener(function (alarm) {
  if (alarm.name === 'reverse-background-search') {
    chrome.storage.local.get(['origin', 'destination', 'depart', 'return'], function (items) {
      if (items.origin && items.destination && items.depart && items.return) {
        handleSearch({
          origin: items.origin,
          destination: items.destination,
          depart: items.depart,
          return: items.return,
        }).then(function (results) {
          console.log('[background] Background search complete:', results.fares.length + ' fares found');
        });
      }
    });
  }
});

// Initial schedule load on startup
chrome.runtime.onStartup.addListener(function () {
  chrome.storage.local.get(['backgroundFrequency'], function (items) {
    updateAlarmSchedule(items.backgroundFrequency || 'disabled');
  });
});
