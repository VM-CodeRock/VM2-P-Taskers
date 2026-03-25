/**
 * VM2-OPP Deep Dive Button Module
 * 
 * Embedded in daily brief and opportunity pages.
 * Creates Todoist tasks via the VM2-OPP API server,
 * OR falls back to the Todoist REST API directly using an injected token.
 * 
 * Usage: Each button has data-* attributes with opportunity metadata.
 *        On click, it calls the API and shows confirmation/error.
 */

(function() {
  'use strict';

  // API endpoint — injected at page generation time
  // Falls back to Todoist REST API if server unavailable
  const TODOIST_API = 'https://api.todoist.com/rest/v2/tasks';
  const TODOIST_TOKEN = window.__VM2_TODOIST_TOKEN || '';
  const VM2_OPP_LABEL_ID = '2183369880';

  // Dedup tracker — solicitation numbers already requested this session
  const requested = new Set();

  // Toast notification
  function showToast(message, type) {
    const toast = document.createElement('div');
    toast.className = 'vm2-toast vm2-toast-' + type;
    toast.innerHTML = message;
    toast.style.cssText = [
      'position:fixed', 'bottom:24px', 'right:24px', 'z-index:9999',
      'padding:14px 20px', 'border-radius:10px', 'font-family:system-ui,sans-serif',
      'font-size:13.5px', 'font-weight:600', 'color:#fff', 'max-width:420px',
      'box-shadow:0 4px 16px rgba(0,0,0,.18)', 'animation:vm2SlideIn .3s ease-out',
      type === 'success' ? 'background:#2D7D4A' :
      type === 'duplicate' ? 'background:#D97D2A' :
      type === 'error' ? 'background:#c53a3a' : 'background:#1B2A4A'
    ].join(';');
    document.body.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; toast.style.transition = 'opacity .3s'; }, 3500);
    setTimeout(() => toast.remove(), 4000);
  }

  // Add animation keyframes
  if (!document.getElementById('vm2-toast-styles')) {
    const style = document.createElement('style');
    style.id = 'vm2-toast-styles';
    style.textContent = '@keyframes vm2SlideIn{from{transform:translateY(20px);opacity:0}to{transform:translateY(0);opacity:1}}';
    document.head.appendChild(style);
  }

  // Create Todoist task via REST API
  async function createTodoistTask(metadata) {
    const taskContent = metadata.solicitation_number
      ? `${metadata.title} — ${metadata.solicitation_number}`
      : metadata.title;

    const metaBlock = JSON.stringify({
      solicitation_number: metadata.solicitation_number || '',
      notice_id: metadata.notice_id || '',
      agency: metadata.agency || '',
      naics: metadata.naics || '',
      rag_score: metadata.rag_score || 0,
      sam_url: metadata.sam_url || '',
      source: metadata.source || 'SAM.gov',
      posted_date: metadata.posted_date || '',
      response_deadline: metadata.response_deadline || '',
      best_match: metadata.best_match || '',
      value_range: metadata.value_range || '',
      requested_at: new Date().toISOString(),
      requested_via: 'deep-dive-button'
    });

    const description = [
      'Deep Dive requested for: ' + metadata.title,
      'Agency: ' + (metadata.agency || 'N/A'),
      'NAICS: ' + (metadata.naics || 'N/A'),
      'RAG Score: ' + (metadata.rag_score || 'N/A'),
      metadata.sam_url ? 'SAM.gov: ' + metadata.sam_url : '',
      '',
      '---VM2-OPP-METADATA---',
      metaBlock,
      '---END-METADATA---'
    ].filter(Boolean).join('\n');

    const response = await fetch(TODOIST_API, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + TODOIST_TOKEN
      },
      body: JSON.stringify({
        content: taskContent,
        description: description,
        label_ids: [VM2_OPP_LABEL_ID],
        labels: ['vm2-opp']
      })
    });

    if (!response.ok) {
      const err = await response.text();
      throw new Error('Todoist API error: ' + response.status + ' ' + err);
    }

    return await response.json();
  }

  // Button click handler
  async function handleDeepDiveClick(event) {
    event.preventDefault();
    const btn = event.currentTarget;

    // Extract metadata from data attributes
    const metadata = {
      title: btn.dataset.title || '',
      solicitation_number: btn.dataset.solNum || '',
      notice_id: btn.dataset.noticeId || '',
      agency: btn.dataset.agency || '',
      naics: btn.dataset.naics || '',
      rag_score: parseFloat(btn.dataset.ragScore) || 0,
      sam_url: btn.dataset.samUrl || '',
      source: btn.dataset.source || 'SAM.gov',
      posted_date: btn.dataset.postedDate || '',
      response_deadline: btn.dataset.responseDeadline || '',
      best_match: btn.dataset.bestMatch || '',
      value_range: btn.dataset.valueRange || ''
    };

    // Check session-level dedup
    const dedupKey = metadata.solicitation_number || metadata.title;
    if (requested.has(dedupKey)) {
      showToast('Deep dive already requested for this opportunity.', 'duplicate');
      return;
    }

    // Update button state
    const originalHTML = btn.innerHTML;
    btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10" stroke-dasharray="31" stroke-dashoffset="31"><animate attributeName="stroke-dashoffset" values="31;0" dur=".8s" repeatCount="indefinite"/></circle></svg> Requesting...';
    btn.style.pointerEvents = 'none';
    btn.style.opacity = '0.7';

    try {
      if (!TODOIST_TOKEN) {
        throw new Error('API token not configured. Use the Todoist quick-add link below instead.');
      }

      const result = await createTodoistTask(metadata);

      // Success
      requested.add(dedupKey);
      btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg> Deep Dive Queued';
      btn.style.background = '#2D7D4A';
      btn.style.opacity = '1';
      showToast('Deep dive queued for <b>' + metadata.title + '</b>. The hourly monitor will generate a full analysis brief.', 'success');

    } catch (err) {
      console.error('Deep dive request failed:', err);
      btn.innerHTML = originalHTML;
      btn.style.pointerEvents = '';
      btn.style.opacity = '1';

      // Fallback: open Todoist quick-add link
      const fallbackUrl = 'https://todoist.com/add?content=' +
        encodeURIComponent((metadata.solicitation_number ? metadata.title + ' — ' + metadata.solicitation_number : metadata.title) + ' @vm2-opp');

      showToast('API unavailable. <a href="' + fallbackUrl + '" target="_blank" style="color:#fff;text-decoration:underline">Click here to add via Todoist</a>', 'error');
    }
  }

  // Initialize all deep-dive buttons on page load
  function init() {
    document.querySelectorAll('.vm2-deep-dive-btn').forEach(btn => {
      btn.addEventListener('click', handleDeepDiveClick);
    });
  }

  // Run on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
