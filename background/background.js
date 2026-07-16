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

// ---- Initialize: always clear stale alarm state ----
chrome.runtime.onInstalled.addListener(function (details) {
  // On every install (fresh install or updates), ensure alarms are
  // cleared. They will be re-created only if the user enables them.
  chrome.alarms.clear('reverse-background-search', function () {
    console.log('[background] Stale alarm cleared on install/update');
  });

  // On first run (no previous settings), show the options page
  // so the user doesn't trigger searches before configuring the extension.
  if (details.reason === 'install') {
    chrome.tabs.create({ url: 'options/options.html' });
  }
});

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

  if (message.action === 'clearAlarm') {
    chrome.alarms.clear('reverse-background-search');
    sendResponse({ success: true });
    return true;
  }
});

/**
 * Concurrency-limited search runner.
 * Executes `queries` in batches of `maxConcurrent`, with
 * `delayMs` between each batch. Prevents service worker timeout.
 *
 * @param {Array<Query>} queries
 * @param {object} settings
 * @returns {Promise<Array<Fare | null>>}
 */
function runWithConcurrency(queries, settings) {
  var maxConcurrent = Math.min(5, queries.length);
  var delayMs = 1500; // 1.5s between batches avoids rate limits
  var results = new Array(queries.length);
  var index = 0;

  return new Promise(function (resolve, reject) {
    function launchBatch() {
      if (index >= queries.length) {
        // All done
        resolve(results);
        return;
      }

      var promises = [];
      var batchEnd = Math.min(index + maxConcurrent, queries.length);

      for (var i = index; i < batchEnd; i++) {
        (function (query, idx) {
          var promise = rateLimitedFetch(function () {
            return fetchFare(query, settings);
          }, { maxRetries: 2, initialDelay: 100 })
            .then(function (fare) { return fare; })
            .catch(function (err) {
              console.warn('[background] Failed to fetch fare for', query.originCode + '→' + query.destinationCode, err);
              return null;
            });
          promises.push(promise.then(function (fare) { results[idx] = fare; return fare; }));
        })(queries[i], i);
      }

      index = batchEnd;

      if (index >= queries.length) {
        Promise.all(promises).then(resolve).catch(reject);
      } else {
        setTimeout(launchBatch, delayMs);
      }
    }

    launchBatch();
  });
}

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

  // Fetch fares for each query with concurrency limiting
  console.log('[background] Generating ' + queries.length + ' queries from ' + data.origin + '→' + data.destination);

  var results = await runWithConcurrency(queries, settings);

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
  if (frequency === 'disabled') {
    chrome.alarms.clear('reverse-background-search');
    console.log('[background] Alarm cleared');
    return;
  }

  chrome.alarms.create('reverse-background-search', {
    periodInMinutes: frequency === 'daily'
      ? 1440
      : frequency === 'weekly'
        ? 10080
        : frequency === '12hours'
          ? 720
          : 1440,
  });

  console.log('[background] Alarm scheduled for every ' + frequency);
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
