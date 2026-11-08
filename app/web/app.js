let allCases = [];
let currentCase = null;
let currentReport = null;

const caseSelect = document.getElementById('case-select');
const btnVerify = document.getElementById('btn-verify');
const btnExportMd = document.getElementById('btn-export-md');
const caseTitle = document.getElementById('case-title');
const sourceCountBadge = document.getElementById('source-count-badge');
const responseTextBox = document.getElementById('response-text');
const sourcesContainer = document.getElementById('sources-container');
const claimCountSpan = document.getElementById('claim-count');
const claimsContainer = document.getElementById('claims-container');

// KPI elements
const kpiGrounding = document.getElementById('kpi-grounding');
const kpiPrecision = document.getElementById('kpi-precision');
const kpiRisk = document.getElementById('kpi-risk');
const kpiBreakdown = document.getElementById('kpi-breakdown');

document.addEventListener('DOMContentLoaded', async () => {
  await loadCases();
});

async function loadCases() {
  try {
    const res = await fetch('/api/benchmark-dataset');
    if (!res.ok) throw new Error('Failed to load benchmark cases');
    const data = await res.json();
    allCases = data.cases || [];

    caseSelect.innerHTML = '';
    allCases.forEach((cs, idx) => {
      const opt = document.createElement('option');
      opt.value = cs.case_id;
      opt.textContent = `${cs.case_id}: ${cs.title}`;
      if (idx === 0) opt.selected = true;
      caseSelect.appendChild(opt);
    });

    if (allCases.length > 0) {
      selectCase(allCases[0]);
    }
  } catch (err) {
    console.error(err);
    alert('Error loading benchmark cases.');
  }
}

caseSelect.addEventListener('change', (e) => {
  const chosen = allCases.find(c => c.case_id === e.target.value);
  if (chosen) selectCase(chosen);
});

function selectCase(c) {
  currentCase = c;
  caseTitle.textContent = `${c.title} (${c.case_id})`;
  sourceCountBadge.textContent = `${c.sources.length} Sources`;
  responseTextBox.textContent = c.chatbot_response;

  sourcesContainer.innerHTML = '';
  c.sources.forEach(src => {
    const div = document.createElement('div');
    div.className = 'source-card';
    div.innerHTML = `
      <div class="source-header">
        <span>[${src.doc_id}] ${escapeHtml(src.title)}</span>
        <span class="source-domain">${escapeHtml(src.domain || 'web')}</span>
      </div>
      <div class="source-snippet">${escapeHtml(src.snippet_text)}</div>
    `;
    sourcesContainer.appendChild(div);
  });

  runVerification(c);
}

btnVerify.addEventListener('click', () => {
  if (currentCase) runVerification(currentCase);
});

async function runVerification(c) {
  const payload = {
    query: c.query || '',
    chatbot_response: c.chatbot_response,
    sources: c.sources
  };

  try {
    const res = await fetch('/api/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error('Verification request failed');
    currentReport = await res.json();
    updateDashboard(currentReport);
  } catch (err) {
    console.error(err);
    alert('Verification error: ' + err.message);
  }
}

function updateDashboard(report) {
  kpiGrounding.textContent = `${(report.grounding_ratio * 100).toFixed(1)}%`;
  kpiPrecision.textContent = `${(report.citation_precision * 100).toFixed(1)}%`;
  kpiRisk.textContent = report.hallucination_risk;

  if (report.hallucination_risk === 'LOW') {
    kpiRisk.style.color = 'var(--success)';
  } else if (report.hallucination_risk === 'MEDIUM') {
    kpiRisk.style.color = 'var(--warning)';
  } else {
    kpiRisk.style.color = 'var(--danger)';
  }

  kpiBreakdown.textContent = `${report.supported_claims}S / ${report.contradicted_claims}C / ${report.unverified_claims}U`;

  claimCountSpan.textContent = report.total_claims;
  claimsContainer.innerHTML = '';

  report.claims.forEach(cl => {
    const card = document.createElement('div');
    card.className = `claim-card status-${cl.status}`;

    card.innerHTML = `
      <div class="claim-card-header">
        <span class="claim-statement"><strong>${cl.claim_id}:</strong> ${escapeHtml(cl.claim_text)}</span>
        <span class="badge badge-${cl.status}">${cl.status}</span>
      </div>
      <div class="claim-meta">
        <span>Cited Doc: <code>${cl.cited_doc_id ? cl.cited_doc_id : 'None'}</code></span>
        <span>Confidence: ${(cl.confidence * 100).toFixed(0)}%</span>
      </div>
      <div class="claim-reasoning">${escapeHtml(cl.reasoning)}</div>
    `;
    claimsContainer.appendChild(card);
  });
}

btnExportMd.addEventListener('click', async () => {
  if (!currentCase) {
    alert('No active case loaded.');
    return;
  }
  const payload = {
    query: currentCase.query || '',
    chatbot_response: currentCase.chatbot_response,
    sources: currentCase.sources
  };
  try {
    const res = await fetch('/api/reports/markdown', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error('Markdown report failed');
    const md = await res.text();
    downloadFile(md, `evidencecheck-${currentCase.case_id}-audit.md`, 'text/markdown');
  } catch (err) {
    console.error(err);
    alert('Error exporting markdown report.');
  }
});

function downloadFile(content, fileName, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/[&<>"']/g, m => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  })[m]);
}
