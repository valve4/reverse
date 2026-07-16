/**
 * popup/popup.js — Handles the popup UI interactions
 * and communicates with the background service worker.
 */

(function () {
  'use strict';

  // ---- DOM refs ----
  var form = document.getElementById('search-form');
  var originInput = document.getElementById('origin');
  var destInput = document.getElementById('destination');
  var departInput = document.getElementById('depart');
  var returnInput = document.getElementById('return');
  var searchBtn = document.getElementById('search-btn');
  var loadingEl = document.getElementById('loading');
  var resultsPanelEl = document.getElementById('results-panel');
  var resultsListEl = document.getElementById('results-list');
  var resultsCountEl = document.getElementById('results-count');
  var emptyStateEl = document.getElementById('empty-state');
  var quickActionsEl = document.getElementById('quick-actions');
  var searchAgainBtn = document.getElementById('search-again-btn');
  var resetBtn = document.getElementById('reset-btn');
  var openSettingsLink = document.getElementById('open-settings');

  // Set default dates to tomorrow and next week
  (function setDefaultDates() {
    var tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    var nextWeek = new Date();
    nextWeek.setDate(nextWeek.getDate() + 8);

    departInput.value = formatDate(tomorrow);
    returnInput.value = formatDate(nextWeek);
  })();

  // ---- Event listeners ----
  form.addEventListener('submit', handleSearch);
  searchAgainBtn.addEventListener('click', handleSearch);
  resetBtn.addEventListener('click', handleReset);
  openSettingsLink.addEventListener('click', function (e) {
    e.preventDefault();
    chrome.tabs.create({ url: 'options/options.html' });
    window.close();
  });

  /**
   * Handle search submission.
   * Reads form data and sends to background service worker.
   *
   * @param {Event} e
   */
  function handleSearch(e) {
    if (e) e.preventDefault();

    var origin = originInput.value.trim();
    var dest = destInput.value.trim();
    var depart = departInput.value;
    var returned = returnInput.value;

    // Validate
    if (!origin || !dest) {
      showFormStatus('Please enter origin and destination cities.', 'error');
      return;
    }

    if (!depart || !returned) {
      showFormStatus('Please select departure and return dates.', 'error');
      return;
    }

    if (new Date(depart) > new Date(returned)) {
      showFormStatus('Departure date must be before return date.', 'error');
      return;
    }

    // Hide results / quick actions while searching
    resultsPanelEl.classList.add('hidden');
    emptyStateEl.classList.add('hidden');
    quickActionsEl.classList.add('hidden');

    setLoading(true);

    // Send search request to background service worker
    chrome.runtime.sendMessage({
      action: 'search',
      data: {
        origin: origin.toLowerCase(),
        destination: dest.toLowerCase(),
        depart: depart,
        return: returned,
        includeReverse: document.getElementById('include-reverse').checked,
      },
    }, function (results) {
      setLoading(false);

      if (chrome.runtime.lastError) {
        showFormStatus('Could not reach background service. Is the extension loaded?', 'error');
        return;
      }

      if (results && results.success && results.fares && results.fares.length > 0) {
        showQuickActions();
        renderResults(results.fares);
      } else if (results && results.success) {
        emptyStateEl.classList.remove('hidden');
        showQuickActions();
      } else {
        showFormStatus(results?.error || 'Search failed. Please try again.', 'error');
      }
    });
  }

  /**
   * Reset the popup to its initial state.
   */
  function handleReset() {
    form.classList.remove('hidden');
    resultsPanelEl.classList.add('hidden');
    emptyStateEl.classList.add('hidden');
    quickActionsEl.classList.add('hidden');

    originInput.value = 'new york';
    destInput.value = 'london';

    var tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    var nextWeek = new Date();
    nextWeek.setDate(nextWeek.getDate() + 8);
    departInput.value = formatDate(tomorrow);
    returnInput.value = formatDate(nextWeek);

    // Remove any status messages
    var statusEl = document.getElementById('form-status');
    if (statusEl) statusEl.remove();
  }

  /**
   * Render fare results in the popup.
   * @param {Array<Fare>} fares — sorted results from background
   */
  function renderResults(fares) {
    resultsPanelEl.classList.remove('hidden');
    resultsListEl.innerHTML = '';

    fares.forEach(function (fare, i) {
      var card = document.createElement('div');
      card.className = 'result-card' + (i === 0 ? ' best' : '');

      // Tag(s)
      var tags = fare.tags || [];
      var tagHtml = tags
        .map(function (tag) {
          var badgeClass = 'badge-' + tag;
          var label = tag.charAt(0).toUpperCase() + tag.slice(1);
          return '<span class="badge ' + badgeClass + '">' + label + '</span>';
        })
        .join(' ');

      // Travel time display
      var travelTime = formatDuration(fare.totalTravelTime);

      // Via info
      var viaHtml = '';
      if (fare.via) {
        viaHtml = '<span class="via"> via ' + fare.via.toUpperCase() + '</span>';
      }

      // Savings display (vs cheapest result)
      var savingsHtml = '';
      if (i > 0 && fare.totalPrice < fares[0].totalPrice) {
        var saved = fares[0].totalPrice - fare.totalPrice;
        savingsHtml =
          '<span class="savings">Save $' + saved.toFixed(0) + ' vs best</span>';
      }

      card.innerHTML =
        '<div class="result-top">' +
        '  <div class="route">' +
        '    <span class="airports">' + fare.originCode + '</span>' +
        '    <span class="arrow">➜</span>' +
        '    <span class="airports">' + fare.destinationCode + '</span>' +
        viaHtml +
        '  </div>' +
        '  <div class="price-row">' +
        '    $' + fare.totalPrice.toFixed(0) +
        (savingsHtml
          ? '<div class="savings-row">' + savingsHtml + '</div>'
          : '') +
        '  </div>' +
        '</div>' +
        '<div class="result-meta">' +
        '  <span class="duration">⏱ ' + travelTime + '</span>' +
        '  <span class="stops">' + (fare.stops === 0 ? 'Nonstop' : fare.stops + ' stop' + (fare.stops > 1 ? 's' : '')) + '</span>' +
        '  ' + tagHtml +
        '</div>';

      // Click to open booking link
      card.addEventListener('click', function () {
        if (fare.bookingUrl) {
          chrome.tabs.create({ url: fare.bookingUrl });
        }
      });

      resultsListEl.appendChild(card);
    });

    resultsCountEl.textContent = fares.length + ' option' + (fares.length !== 1 ? 's' : '');

    // Update loading count
    var loadingCountEl = document.getElementById('loading-count');
    if (loadingCountEl) loadingCountEl.textContent = fares.length;
  }

  /**
   * Show the quick actions bar (Search Again / Reset).
   */
  function showQuickActions() {
    quickActionsEl.classList.remove('hidden');
  }

  /**
   * Toggle loading state.
   * @param {boolean} loading
   */
  function setLoading(loading) {
    searchBtn.disabled = loading;

    if (loading) {
      document.querySelector('.btn-text').textContent = 'Searching...';
      document.querySelector('.btn-spinner').hidden = false;
      loadingEl.classList.remove('hidden');
      resultsPanelEl.classList.add('hidden');
      emptyStateEl.classList.add('hidden');
    } else {
      document.querySelector('.btn-text').textContent = 'Search All Routes';
      document.querySelector('.btn-spinner').hidden = true;
      loadingEl.classList.add('hidden');
    }
  }

  /**
   * Show inline error/warning on the form.
   * @param {string} message
   * @param {string} [type='error']
   */
  function showFormStatus(message, type) {
    // Remove any existing status message
    var existing = document.getElementById('form-status');
    if (existing) existing.remove();

    var statusEl = document.createElement('div');
    statusEl.id = 'form-status';
    statusEl.textContent = message;
    statusEl.style.cssText =
      'padding: 10px 14px; border-radius: 8px; ' +
      'background: ' + (type === 'error' ? '#fce8e6' : '#e6f4ea') + '; ' +
      'color: ' + (type === 'error' ? '#c5221f' : '#0d8a4e') + '; ' +
      'font-size: 13px; font-weight: 500;';

    form.insertBefore(statusEl, form.firstChild);

    // Auto-hide after 4 seconds
    setTimeout(function () {
      statusEl.remove();
    }, 4000);
  }

  // ---- Utility functions ----

  /**
   * Format a Date object to YYYY-MM-DD.
   * @param {Date} d
   * @returns {string}
   */
  function formatDate(d) {
    var y = d.getFullYear();
    var m = String(d.getMonth() + 1).padStart(2, '0');
    var day = String(d.getDate()).padStart(2, '0');
    return y + '-' + m + '-' + day;
  }

  /**
   * Format milliseconds duration to human-readable string.
   * @param {number} ms
   * @returns {string}
   */
  function formatDuration(ms) {
    if (!ms || ms <= 0) return '—';
    var hours = Math.floor(ms / 3600000);
    var mins = Math.floor((ms % 3600000) / 60000);
    if (hours > 0 && mins > 0) return hours + 'h ' + mins + 'm';
    if (hours > 0) return hours + 'h';
    return mins + 'm';
  }
})();
