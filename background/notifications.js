/**
 * background/notifications.js — Desktop + email alert logic
 *
 * Handles showing desktop notifications when a deal is found,
 * and sending email alerts for $50+ price drops.
 */

/**
 * Check if any fares are a "big drop" vs. the previous results
 * and trigger notifications for each.
 *
 * @param {Array<Fare>} newFares — sorted by price asc
 * @param {object} settings
 * @param {Array<Fare>} [previousFares] — previous search results
 * @returns {{desktopShown: boolean, emailSent: boolean, bigDropFare: Fare|null}}
 */
async function checkForBigDrops(newFares, settings, previousFares) {
  if (!newFares || newFares.length === 0) return { desktopShown: false, emailSent: false, bigDropFare: null };

  var threshold = settings.emailThreshold || 50;

  // Determine the best fare from the previous search
  var prevBest = previousFares && previousFares.length > 0
    ? previousFares[0]
    : null;

  var bestNew = newFares[0];
  var isBigDrop = prevBest && (prevBest.totalPrice - bestNew.totalPrice) >= threshold;

  var desktopShown = false;
  var emailSent = false;

  // Always show desktop notification
  await showDesktopNotification(bestNew);
  desktopShown = true;

  // Email if big drop threshold is met
  if (isBigDrop && settings.email) {
    var savings = prevBest.totalPrice - bestNew.totalPrice;
    emailSent = await sendEmailAlert(bestNew, savings, settings.email);
    if (emailSent) {
      // Store the previous best price for next comparison
      await chrome.storage.local.set({
        lastBestPrice: bestNew.totalPrice,
        lastSearchDate: new Date().toISOString(),
      });
    }
  }

  return {
    desktopShown: desktopShown,
    emailSent: emailSent,
    bigDropFare: isBigDrop ? bestNew : null,
  };
}

/**
 * Show a Chrome desktop notification.
 *
 * @param {Fare} fare
 * @returns {Promise<void>}
 */
async function showDesktopNotification(fare) {
  try {
    var title = 'Reverse: ' + fare.originCode + ' → ' + fare.destinationCode + ' — $' + fare.totalPrice.toFixed(0);
    var message = 'Total travel time: ' + formatDuration(fare.totalTravelTime) +
      (fare.tags && fare.tags.length > 0 ? (' — ' + fare.tags.join(', ')) : '');

    await chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icons/icon128.png',
      title: title,
      message: message,
      priority: 2, // highest priority
    });
  } catch (err) {
    console.error('[notifications] Desktop notification error:', err);
  }
}

/**
 * Send an email alert via a webhook or SMTP API.
 * Currently uses a simple POST to a webhook endpoint —
 * replace with your preferred email service (Resend, Mailgun, etc.).
 *
 * @param {Fare} fare
 * @param {number} savings
 * @param {string} recipientEmail
 * @returns {Promise<boolean>}
 */
async function sendEmailAlert(fare, savings, recipientEmail) {
  // For development, just log the alert
  console.log('[notifications] Email alert would be sent:', {
    to: recipientEmail,
    fare: fare,
    savings: '$' + savings.toFixed(0),
  });

  // TODO: Replace with real email integration
  // Example with Resend API:
  //   var response = await fetch('https://api.resend.com/emails', {
  //     method: 'POST',
  //     headers: {
  //       'Authorization': 'Bearer ' + RESEND_API_KEY,
  //       'Content-Type': 'application/json',
  //     },
  //     body: JSON.stringify({
  //       from: 'Reverse <hello@reverse.flight>',
  //       to: [recipientEmail],
  //       subject: 'New fare drop: ' + fare.originCode + ' → ' + fare.destinationCode,
  //       html: buildEmailHTML(fare, savings),
  //     }),
  //   });

  return true;
}

/**
 * Build HTML email body for fare drop alert.
 *
 * @param {Fare} fare
 * @param {number} savings
 * @returns {string}
 */
function buildEmailHTML(fare, savings) {
  return '<div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">' +
    '<h2 style="color: #1a73e8;">💰 New fare drop for ' + fare.originCode + ' → ' + fare.destinationCode + '</h2>' +
    '<p style="font-size: 16px;">Price: <strong>$' + fare.totalPrice.toFixed(0) + '</strong></p>' +
    '<p style="font-size: 16px;">You save: <strong style="color: green;">$' + savings.toFixed(0) + '</strong></p>' +
    '<p style="font-size: 14px; color: #666;">' + formatDuration(fare.totalTravelTime) +
    (fare.tags && fare.tags.length > 0 ? (' • ' + fare.tags.join(', ')) : '') + '</p>' +
    '<p style="margin-top: 20px; font-size: 12px; color: #999;">' +
    'To book, click the Reverse extension icon → click on this fare.</p>' +
    '</div>';
}

/**
 * Format milliseconds to human-readable duration.
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

export { checkForBigDrops, buildEmailHTML };
