/**
 * options/options.js — Settings page logic
 * Loads and saves user configuration to chrome.storage.local
 */

(function () {
  'use strict';

  // ---- DOM refs ----
  var form = document.getElementById('settings-form');
  var apiProviderInput = document.getElementById('api-provider');
  var apiKeyInput = document.getElementById('api-key');
  var apiSecretInput = document.getElementById('api-secret');
  var emailInput = document.getElementById('email');
  var emailThresholdInput = document.getElementById('email-threshold');
  var currencyInput = document.getElementById('currency');
  var maxResultsInput = document.getElementById('max-results');
  var includeReverseInput = document.getElementById('include-reverse');
  var includeSplitInput = document.getElementById('include-split');
  var clearDataBtn = document.getElementById('clear-data-btn');
  var saveStatus = document.getElementById('save-status');

  // Default settings
  var DEFAULTS = {
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
  };

  /**
   * Load saved settings on page load.
   */
  function loadSettings() {
    chrome.storage.local.get(Object.keys(DEFAULTS), function (items) {
      if (!chrome.runtime.lastError) {
        apiProviderInput.value = items.apiProvider || DEFAULTS.apiProvider;
        apiKeyInput.value = items.apiKey || '';
        apiSecretInput.value = items.apiSecret || '';
        emailInput.value = items.email || '';
        emailThresholdInput.value = items.emailThreshold || DEFAULTS.emailThreshold;

        // Set radio button
        var radios = document.getElementsByName('background-frequency');
        var freq = items.backgroundFrequency || DEFAULTS.backgroundFrequency;
        for (var i = 0; i < radios.length; i++) {
          if (radios[i].value === freq) {
            radios[i].checked = true;
          }
        }

        currencyInput.value = items.currency || DEFAULTS.currency;
        maxResultsInput.value = items.maxResults || DEFAULTS.maxResults;
        includeReverseInput.checked = (items.includeReverse !== undefined)
          ? items.includeReverse
          : DEFAULTS.includeReverse;
        includeSplitInput.checked = (items.includeSplit !== undefined)
          ? items.includeSplit
          : DEFAULTS.includeSplit;
      }
    });
  }

  /**
   * Save settings from the form to chrome.storage.local.
   *
   * @param {Event} e
   */
  function saveSettings(e) {
    e.preventDefault();

    // Get radio value
    var radios = document.getElementsByName('background-frequency');
    var freq = 'disabled';
    for (var i = 0; i < radios.length; i++) {
      if (radios[i].checked) {
        freq = radios[i].value;
        break;
      }
    }

    var settings = {
      apiProvider: apiProviderInput.value,
      apiKey: apiKeyInput.value.trim(),
      apiSecret: apiSecretInput.value.trim(),
      email: emailInput.value.trim(),
      emailThreshold: parseInt(emailThresholdInput.value, 10) || DEFAULTS.emailThreshold,
      backgroundFrequency: freq,
      currency: currencyInput.value,
      maxResults: parseInt(maxResultsInput.value, 10) || DEFAULTS.maxResults,
      includeReverse: includeReverseInput.checked,
      includeSplit: includeSplitInput.checked,
    };

    chrome.storage.local.set(settings, function () {
      if (chrome.runtime.lastError) {
        showStatus('Error saving settings: ' + chrome.runtime.lastError.message, true);
      } else {
        showStatus('Settings saved!');

        // Update background service worker schedule if needed
        chrome.runtime.sendMessage({
          action: 'updateSchedule',
          frequency: freq,
        });
      }
    });
  }

  /**
   * Clear all saved data.
   *
   * @param {Event} e
   */
  function clearData(e) {
    if (!confirm('Clear all saved data? This cannot be undone.')) return;

    chrome.storage.local.clear(function () {
      if (chrome.runtime.lastError) {
        showStatus('Error clearing data: ' + chrome.runtime.lastError.message, true);
      } else {
        showStatus('All data cleared. Reloading...');
        // Reset form to defaults
        setTimeout(function () {
          loadSettings();
        }, 1000);
      }
    });
  }

  /**
   * Show status message next to save button.
   *
   * @param {string} message
   * @param {boolean} [isError=false]
   */
  function showStatus(message, isError) {
    saveStatus.textContent = message;
    saveStatus.classList.toggle('error', !!isError);

    setTimeout(function () {
      saveStatus.textContent = '';
      saveStatus.classList.remove('error');
    }, 3000);
  }

  // ---- Event listeners ----
  form.addEventListener('submit', saveSettings);
  clearDataBtn.addEventListener('click', clearData);

  // Load on init
  loadSettings();
})();
