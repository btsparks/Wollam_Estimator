/* ============================================================
   WEIS v2 — Frontend Application
   Single-page app with vanilla JS routing
   ============================================================ */

// ── State ──
const state = {
    currentPage: 'interview',
    currentJobId: null,
    jobs: [],
    jobDetail: null,
    selectedCostCode: null,
    filter: 'all',
    jobStatusFilter: 'all',
    searchQuery: '',
    viewMode: 'card',       // 'card' or 'table'
    sortField: 'data_richness',
    sortDir: 'desc',
    progress: null,
    ccSortDir: 'asc',       // 'asc' or 'desc' for cost code list
    // Chat state
    chatConversationId: null,
    chatConversations: [],
    chatMessages: [],
    chatLoading: false,
    chatDataSummary: null,
};

// ── API Helpers ──
async function api(endpoint, options = {}) {
    const res = await fetch(`/api${endpoint}`, {
        headers: { 'Content-Type': 'application/json', ...options.headers },
        ...options,
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'API error');
    }
    return res.json();
}

// ── Navigation ──
function navigate(page, jobId = null) {
    state.currentPage = page;
    state.currentJobId = jobId;
    state.selectedCostCode = null;
    estSelectedBidItemId = null;
    estSelectedActivityId = null;
    estExpandedBidItems = new Set();

    // Reset content area styles (chat uses custom layout)
    const contentArea = document.getElementById('contentArea');
    const content = document.getElementById('content');
    if (page !== 'chat') {
        contentArea.style.padding = '';
        contentArea.style.display = '';
        content.style.maxWidth = '';
        content.style.margin = '';
        content.style.width = '';
        content.style.display = '';
        content.style.height = '';
    }

    // Update sidebar active
    document.querySelectorAll('.sidebar-nav a').forEach(a => {
        a.classList.toggle('active', a.dataset.page === page);
    });

    if (page === 'interview' && jobId) {
        loadJobDetail(jobId);
    } else if (page === 'interview') {
        loadJobList();
    } else if (page === 'chat') {
        renderChat();
    } else if (page === 'estimates' && jobId) {
        loadEstimateDetail(jobId);
    } else if (page === 'estimates') {
        loadEstimateList();
    } else if (page === 'settings') {
        renderSettings();
    }
}

// ── Format Helpers ──
function fmt(n, decimals = 0) {
    if (n == null) return '—';
    return Number(n).toLocaleString('en-US', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    });
}

function fmtRate(n) {
    if (n == null) return '—';
    if (n >= 1) return fmt(n, 2);
    if (n >= 0.1) return fmt(n, 2);
    return fmt(n, 4);
}

function confidenceBadge(level) {
    if (!level) return '<span class="badge badge-none">NO DATA</span>';
    const l = level.toLowerCase();
    if (l === 'strong' || l === 'high') return `<span class="badge badge-high">HIGH</span>`;
    if (l === 'moderate') return `<span class="badge badge-moderate">MODERATE</span>`;
    if (l === 'limited' || l === 'low') return `<span class="badge badge-limited">LOW</span>`;
    return `<span class="badge badge-none">${level.toUpperCase()}</span>`;
}

function interviewBadge(status) {
    const map = {
        complete: '<span class="badge badge-complete">Complete</span>',
        in_progress: '<span class="badge badge-in-progress">In Progress</span>',
        not_started: '<span class="badge badge-not-started">Not Started</span>',
    };
    return map[status] || map.not_started;
}

function jobStatusBadge(status) {
    if (status === 'active') return '<span class="badge badge-active">Active</span>';
    if (status === 'completed') return '<span class="badge badge-completed">Completed</span>';
    return `<span class="badge badge-not-started">${status || 'Unknown'}</span>`;
}

// ── Load Job List ──
async function loadJobList() {
    const content = document.getElementById('content');
    document.getElementById('pageTitle').textContent = 'PM Context Interview';
    document.getElementById('pageSubtitle').textContent = 'Capture institutional knowledge from your project managers';

    content.innerHTML = '<div class="empty-state"><p>Loading jobs...</p></div>';

    try {
        const [jobs, progress] = await Promise.all([
            api('/interview/jobs'),
            api('/interview/progress'),
        ]);
        state.jobs = jobs;
        renderJobList(jobs, progress);
    } catch (err) {
        content.innerHTML = `<div class="empty-state"><h3>Error loading jobs</h3><p>${err.message}</p></div>`;
    }
}

function renderJobList(jobs, progress) {
    const content = document.getElementById('content');
    if (progress) state.progress = progress;
    const p = state.progress || {};

    // Apply filters
    let filtered = jobs;
    if (state.jobStatusFilter !== 'all') {
        filtered = filtered.filter(j => j.status === state.jobStatusFilter);
    }
    if (state.filter !== 'all') {
        filtered = filtered.filter(j => j.interview_status === state.filter);
    }
    if (state.searchQuery) {
        const q = state.searchQuery.toLowerCase();
        filtered = filtered.filter(j =>
            j.job_number.toLowerCase().includes(q) ||
            j.name.toLowerCase().includes(q)
        );
    }

    // Count jobs by status for the filter tabs
    const activeCount = jobs.filter(j => j.status === 'active').length;
    const completedCount = jobs.filter(j => j.status === 'completed').length;

    // Sort
    filtered = sortJobs(filtered, state.sortField, state.sortDir);

    const isTable = state.viewMode === 'table';

    content.innerHTML = `
        <!-- KPI Cards -->
        <div class="kpi-grid">
            <div class="kpi-card card-animate">
                <div class="kpi-label">Total Jobs</div>
                <div class="kpi-value">${fmt(p.total_jobs)}</div>
            </div>
            <div class="kpi-card card-animate">
                <div class="kpi-label">Interviews Started</div>
                <div class="kpi-value">${fmt(p.jobs_with_context)}</div>
            </div>
            <div class="kpi-card card-animate">
                <div class="kpi-label">Interviews Complete</div>
                <div class="kpi-value">${fmt(p.jobs_complete)}</div>
            </div>
            <div class="kpi-card card-animate">
                <div class="kpi-label">Cost Codes with Context</div>
                <div class="kpi-value">${fmt(p.cost_codes_with_context)}<span style="font-size: 14px; font-weight: 500; color: var(--text-tertiary);"> / ${fmt(p.total_cost_codes_with_data)}</span></div>
            </div>
        </div>

        <!-- Diary Import -->
        <div class="diary-section card-animate" id="diaryImportSection">
            <div class="diary-header">
                <div class="diary-title">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
                    HeavyJob Diary Notes
                </div>
                <button class="btn btn-sm" onclick="importDiaries()" id="importDiaryBtn">Import Diary Files</button>
            </div>
            <div class="diary-stats" id="diaryStats">
                ${getDiaryStatsHtml(jobs)}
            </div>
        </div>

        <!-- Toolbar: Filters + Search + View Toggle -->
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px; flex-wrap: wrap;">
            <div class="filter-tabs">
                <button class="filter-tab ${state.jobStatusFilter === 'all' ? 'active' : ''}" onclick="setJobStatusFilter('all')">All Jobs (${jobs.length})</button>
                <button class="filter-tab ${state.jobStatusFilter === 'active' ? 'active' : ''}" onclick="setJobStatusFilter('active')">Active (${activeCount})</button>
                <button class="filter-tab ${state.jobStatusFilter === 'completed' ? 'active' : ''}" onclick="setJobStatusFilter('completed')">Completed (${completedCount})</button>
            </div>
            <div class="filter-tabs">
                <button class="filter-tab ${state.filter === 'all' ? 'active' : ''}" onclick="setFilter('all')">All</button>
                <button class="filter-tab ${state.filter === 'not_started' ? 'active' : ''}" onclick="setFilter('not_started')">Not Started</button>
                <button class="filter-tab ${state.filter === 'in_progress' ? 'active' : ''}" onclick="setFilter('in_progress')">In Progress</button>
                <button class="filter-tab ${state.filter === 'complete' ? 'active' : ''}" onclick="setFilter('complete')">Complete</button>
            </div>
            <div class="search-wrapper" style="flex: 1; min-width: 200px; max-width: 320px; margin-bottom: 0;">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                <input type="text" class="search-input" placeholder="Search jobs..." value="${state.searchQuery}" oninput="setSearch(this.value)">
            </div>
            <span id="jobFilterCount" style="font-size: 12px; color: var(--text-tertiary);">${filtered.length} job${filtered.length !== 1 ? 's' : ''}</span>
            <div class="view-toggle">
                <button class="view-toggle-btn ${!isTable ? 'active' : ''}" onclick="setViewMode('card')" title="Card view" aria-label="Card view">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
                </button>
                <button class="view-toggle-btn ${isTable ? 'active' : ''}" onclick="setViewMode('table')" title="Table view" aria-label="Table view">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
                </button>
            </div>
        </div>

        <!-- Job List: Card or Table -->
        <div id="jobListArea">
        ${isTable ? renderJobTable(filtered) : renderJobGrid(filtered)}
        </div>
    `;
}

function renderJobGrid(filtered) {
    if (filtered.length === 0) {
        return '<div class="empty-state"><h3>No jobs match your filters</h3><p>Try adjusting your search or filter criteria.</p></div>';
    }
    return `<div class="job-grid">${filtered.map(j => renderJobCard(j)).join('')}</div>`;
}

function renderJobTable(filtered) {
    if (filtered.length === 0) {
        return '<div class="empty-state"><h3>No jobs match your filters</h3><p>Try adjusting your search or filter criteria.</p></div>';
    }

    const sortIcon = (field) => {
        if (state.sortField !== field) return '<span class="sort-icon">&#8597;</span>';
        return state.sortDir === 'asc'
            ? '<span class="sort-icon active">&#8593;</span>'
            : '<span class="sort-icon active">&#8595;</span>';
    };

    return `
        <div class="card" style="overflow-x: auto;">
            <table class="data-table">
                <thead>
                    <tr>
                        <th class="sortable" onclick="toggleSort('job_number')">Job # ${sortIcon('job_number')}</th>
                        <th class="sortable" onclick="toggleSort('name')">Name ${sortIcon('name')}</th>
                        <th class="sortable" onclick="toggleSort('status')" style="text-align: center;">Status ${sortIcon('status')}</th>
                        <th class="sortable" onclick="toggleSort('cost_code_count')" style="text-align: right;">Cost Codes ${sortIcon('cost_code_count')}</th>
                        <th class="sortable" onclick="toggleSort('cost_codes_with_data')" style="text-align: right;">With Data ${sortIcon('cost_codes_with_data')}</th>
                        <th class="sortable" onclick="toggleSort('data_richness')" style="text-align: right;">Richness ${sortIcon('data_richness')}</th>
                        <th class="sortable" onclick="toggleSort('cost_codes_with_context')" style="text-align: right;">Context ${sortIcon('cost_codes_with_context')}</th>
                        <th class="sortable" onclick="toggleSort('interview_status')" style="text-align: center;">Interview ${sortIcon('interview_status')}</th>
                    </tr>
                </thead>
                <tbody>
                    ${filtered.map(j => {
                        const contextPct = j.cost_codes_with_data > 0
                            ? Math.round((j.cost_codes_with_context / j.cost_codes_with_data) * 100) : 0;
                        return `
                        <tr class="data-row" onclick="navigate('interview', ${j.job_id})">
                            <td style="font-weight: 700; color: var(--wollam-navy);">${j.job_number}</td>
                            <td style="max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${j.name || '—'}</td>
                            <td style="text-align: center;">${jobStatusBadge(j.status)}</td>
                            <td style="text-align: right; font-variant-numeric: tabular-nums;">${fmt(j.cost_code_count)}</td>
                            <td style="text-align: right; font-variant-numeric: tabular-nums;">${fmt(j.cost_codes_with_data)}</td>
                            <td style="text-align: right;">
                                <div style="display: flex; align-items: center; gap: 8px; justify-content: flex-end;">
                                    <div class="progress-bar" style="width: 60px; height: 4px;">
                                        <div class="progress-fill navy" style="width: ${j.data_richness}%"></div>
                                    </div>
                                    <span style="font-variant-numeric: tabular-nums; min-width: 32px; text-align: right;">${j.data_richness}%</span>
                                </div>
                            </td>
                            <td style="text-align: right;">
                                <span style="font-variant-numeric: tabular-nums;">${j.cost_codes_with_context}</span>
                                <span style="color: var(--text-tertiary); font-size: 11px;"> / ${j.cost_codes_with_data}</span>
                                ${contextPct > 0 ? `<span style="color: var(--text-tertiary); font-size: 11px;"> (${contextPct}%)</span>` : ''}
                            </td>
                            <td style="text-align: center;">${interviewBadge(j.interview_status)}</td>
                        </tr>`;
                    }).join('')}
                </tbody>
            </table>
        </div>
    `;
}

function sortJobs(jobs, field, dir) {
    return [...jobs].sort((a, b) => {
        let va = a[field];
        let vb = b[field];
        // Handle strings
        if (typeof va === 'string') va = va.toLowerCase();
        if (typeof vb === 'string') vb = vb.toLowerCase();
        // Handle nulls
        if (va == null) va = '';
        if (vb == null) vb = '';
        if (va < vb) return dir === 'asc' ? -1 : 1;
        if (va > vb) return dir === 'asc' ? 1 : -1;
        return 0;
    });
}

function toggleSort(field) {
    if (state.sortField === field) {
        state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
    } else {
        state.sortField = field;
        state.sortDir = field === 'name' || field === 'job_number' ? 'asc' : 'desc';
    }
    renderJobList(state.jobs);
}

function setViewMode(mode) {
    state.viewMode = mode;
    renderJobList(state.jobs);
}

function renderJobCard(job) {
    const contextPct = job.cost_codes_with_data > 0
        ? Math.round((job.cost_codes_with_context / job.cost_codes_with_data) * 100)
        : 0;

    return `
        <div class="card card-clickable card-animate" onclick="navigate('interview', ${job.job_id})">
            <div class="job-card">
                <div class="job-card-header">
                    <span class="job-number">Job ${job.job_number}</span>
                    <div style="display: flex; gap: 6px; align-items: center;">
                        ${jobStatusBadge(job.status)}
                        ${interviewBadge(job.interview_status)}
                    </div>
                </div>
                <div class="job-name">${job.name || 'Untitled Job'}</div>
                <div class="job-stats">
                    ${fmt(job.cost_code_count)} cost codes &middot; ${fmt(job.cost_codes_with_data)} with data
                    ${job.diary_entry_count > 0 ? ` &middot; <span class="badge badge-diary" style="font-size: 10px; padding: 1px 6px;">${fmt(job.diary_entry_count)} diary</span>` : ''}
                </div>
                <div style="margin-bottom: 8px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span class="progress-label">Data Richness</span>
                        <span class="progress-label">${job.data_richness}%</span>
                    </div>
                    <div class="progress-bar"><div class="progress-fill navy" style="width: ${job.data_richness}%"></div></div>
                </div>
                ${job.cost_codes_with_data > 0 ? `
                <div>
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span class="progress-label">Context Coverage</span>
                        <span class="progress-label">${job.cost_codes_with_context} of ${job.cost_codes_with_data} (${contextPct}%)</span>
                    </div>
                    <div class="progress-bar"><div class="progress-fill green" style="width: ${contextPct}%"></div></div>
                </div>
                ` : ''}
            </div>
        </div>
    `;
}

function setFilter(f) {
    state.filter = f;
    renderJobList(state.jobs);
}

function setJobStatusFilter(f) {
    state.jobStatusFilter = f;
    renderJobList(state.jobs);
}

function setSearch(q) {
    state.searchQuery = q;
    // Only re-render the job list area, not the whole page (preserves search input focus)
    const listContainer = document.getElementById('jobListArea');
    if (listContainer) {
        let filtered = state.jobs;
        if (state.jobStatusFilter !== 'all') filtered = filtered.filter(j => j.status === state.jobStatusFilter);
        if (state.filter !== 'all') filtered = filtered.filter(j => j.interview_status === state.filter);
        if (state.searchQuery) {
            const sq = state.searchQuery.toLowerCase();
            filtered = filtered.filter(j => j.job_number.toLowerCase().includes(sq) || j.name.toLowerCase().includes(sq));
        }
        filtered = sortJobs(filtered, state.sortField, state.sortDir);
        const isTable = state.viewMode === 'table';
        listContainer.innerHTML = isTable ? renderJobTable(filtered) : renderJobGrid(filtered);
        // Update count
        const countEl = document.getElementById('jobFilterCount');
        if (countEl) countEl.textContent = `${filtered.length} job${filtered.length !== 1 ? 's' : ''}`;
    } else {
        renderJobList(state.jobs);
    }
}

// ── Load Job Detail (Interview Page) ──
async function loadJobDetail(jobId) {
    const content = document.getElementById('content');
    content.innerHTML = '<div class="empty-state"><p>Loading job detail...</p></div>';

    try {
        const [data, recast, linkedEstimates] = await Promise.all([
            api(`/interview/job/${jobId}`),
            api(`/settings/recast/${jobId}`).catch(() => null),
            api(`/estimates/?linked_job_id=${jobId}`).catch(() => []),
        ]);
        state.jobDetail = data;
        state.recastCosts = recast;
        state.linkedEstimates = linkedEstimates || [];
        state.selectedCostCode = data.cost_codes.length > 0 ? data.cost_codes[0].code : null;

        document.getElementById('pageTitle').textContent = `Job ${data.job.job_number}`;
        document.getElementById('pageSubtitle').textContent = data.job.name;

        renderJobDetail(data);

        // Load document list async (after render so the container exists)
        loadDocList(jobId);

        // Set up drag-and-drop on the upload area
        initDocUploadArea(jobId);
    } catch (err) {
        content.innerHTML = `<div class="empty-state"><h3>Error</h3><p>${err.message}</p></div>`;
    }
}

function renderJobDetail(data) {
    const content = document.getElementById('content');
    const job = data.job;
    const pm = data.pm_context || {};
    const codes = data.cost_codes;
    const contextCount = codes.filter(c => c.has_context).length;

    // Build "View Estimate" link if linked
    const estLinks = (state.linkedEstimates || []);
    const estLinkHtml = estLinks.length > 0
        ? estLinks.map(e => `<button onclick="navigate('estimates',${e.estimate_id})" style="padding:6px 16px;background:rgba(37,99,235,0.1);color:var(--wollam-blue);border:1px solid rgba(37,99,235,0.2);border-radius:8px;cursor:pointer;font-size:13px;font-weight:500;">View Estimate: ${escHtml(e.code || '')} &rarr;</button>`).join(' ')
        : '';

    content.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <button class="back-btn" onclick="navigate('interview')">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
                Back to Jobs
            </button>
            <div>${estLinkHtml}</div>
        </div>

        <!-- Top Bar -->
        <div class="interview-topbar">
            <div class="topbar-info">
                <h2>Job ${job.job_number} — ${job.name} ${jobStatusBadge(job.status)}</h2>
                <span class="subtitle">${fmt(job.cost_codes_with_data)} cost codes with data &middot; ${contextCount} with context</span>
            </div>
            <div class="topbar-progress">
                <div class="count">${contextCount} / ${codes.length} reviewed</div>
                <div class="progress-bar" style="width: 160px;">
                    <div class="progress-fill green" style="width: ${codes.length > 0 ? (contextCount / codes.length * 100) : 0}%"></div>
                </div>
            </div>
        </div>

        <!-- Job Overview -->
        <div class="overview-section">
            <div class="overview-title">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--wollam-navy)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>
                Job Overview
            </div>
            <div class="data-grid" style="grid-template-columns: repeat(3, 1fr); margin-bottom: 20px;">
                <div class="data-item">
                    <div class="data-item-label">Actual Hours</div>
                    <div class="data-item-value">${fmt(job.total_actual_hrs)}</div>
                </div>
                <div class="data-item">
                    <div class="data-item-label">Budget Hours</div>
                    <div class="data-item-value">${fmt(job.total_budget_hrs)}</div>
                </div>
                <div class="data-item">
                    <div class="data-item-label">Cost Codes</div>
                    <div class="data-item-value">${fmt(job.cost_codes_with_data)}<span style="font-size: 12px; color: var(--text-tertiary);"> / ${fmt(job.total_cost_codes)}</span></div>
                </div>
            </div>

            <!-- Cost Comparison Table -->
            <table class="cost-comparison-table">
                <thead>
                    <tr>
                        <th></th>
                        <th>Labor</th>
                        <th>Equipment</th>
                        <th>Material</th>
                        <th>Subs</th>
                        <th>Total</th>
                    </tr>
                </thead>
                <tbody>
                    ${job.total_budget_cost ? `
                    <tr class="cost-row-budget">
                        <td class="cost-row-label">Budget</td>
                        <td>$${fmt(job.total_budget_labor_cost)}</td>
                        <td>$${fmt(job.total_budget_equip_cost)}</td>
                        <td>$${fmt(job.total_budget_matl_cost)}</td>
                        <td>$${fmt(job.total_budget_sub_cost)}</td>
                        <td class="cost-row-total">$${fmt(job.total_budget_cost)}</td>
                    </tr>` : ''}
                    ${job.total_actual_cost ? `
                    <tr class="cost-row-actual">
                        <td class="cost-row-label"><span class="cost-dot cost-dot-actual"></span>Actual</td>
                        <td>$${fmt(job.total_actual_labor_cost)}</td>
                        <td>$${fmt(job.total_actual_equip_cost)}</td>
                        <td>$${fmt(job.total_actual_matl_cost)}</td>
                        <td>$${fmt(job.total_actual_sub_cost)}</td>
                        <td class="cost-row-total">$${fmt(job.total_actual_cost)}</td>
                    </tr>` : ''}
                    ${state.recastCosts ? `
                    <tr class="cost-row-recast">
                        <td class="cost-row-label"><span class="cost-dot cost-dot-recast"></span>Recast <span class="cost-row-hint">2026 rates</span></td>
                        <td>$${fmt(state.recastCosts.job_totals.labor_cost)}</td>
                        <td>$${fmt(state.recastCosts.job_totals.equip_cost)}</td>
                        <td class="cost-cell-na">--</td>
                        <td class="cost-cell-na">--</td>
                        <td class="cost-row-total">$${fmt(state.recastCosts.job_totals.total_cost)}</td>
                    </tr>` : ''}
                </tbody>
            </table>
        </div>

        <!-- Diary Intelligence Section -->
        ${data.diary_summary ? `
        <div class="diary-section">
            <div class="diary-header">
                <div class="diary-title">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
                    Diary Intelligence Available
                </div>
                <button class="btn btn-sm" id="synthesizeBtn" onclick="synthesizeDiary(${job.job_id})"
                    style="background: rgba(139,92,246,0.1); color: #7C3AED; border-color: rgba(139,92,246,0.3);">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                    Synthesize with AI
                </button>
            </div>
            <div class="diary-stats">
                <span><span class="diary-stat-value">${fmt(data.diary_summary.entry_count)}</span> diary entries</span>
                <span><span class="diary-stat-value">${data.diary_summary.cost_code_count}</span> cost codes</span>
                <span><span class="diary-stat-value">${data.diary_summary.foreman_count}</span> foremen</span>
                <span>${data.diary_summary.date_start} to ${data.diary_summary.date_end}</span>
            </div>
            ${data.diary_summary.foremen ? `
            <div style="margin-top: 8px; font-size: 12px; color: var(--text-tertiary);">
                Foremen: ${data.diary_summary.foremen.join(', ')}
            </div>` : ''}
        </div>
        ` : ''}

        <!-- Document Upload Section -->
        <div class="doc-section" id="docSection">
            <div class="doc-header">
                <div class="doc-title">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
                    Project Documents
                    ${data.doc_summary ? `<span style="font-size: 12px; font-weight: 400; color: var(--text-secondary); margin-left: 4px;">(${data.doc_summary.doc_count})</span>` : ''}
                </div>
                <div style="display: flex; gap: 8px;">
                    ${data.doc_summary && data.doc_summary.doc_count > 0 ? `
                    <button class="btn btn-sm" id="enrichBtn" onclick="enrichFromDocs(${job.job_id})"
                        style="background: rgba(14,165,233,0.1); color: #0284C7; border-color: rgba(14,165,233,0.3);">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                        Enrich with AI
                    </button>` : ''}
                </div>
            </div>

            <!-- Upload area -->
            <div class="doc-upload-area" id="docUploadArea" onclick="document.getElementById('docFileInput').click()">
                <input type="file" id="docFileInput" style="display:none" accept=".pdf,.xlsx,.xls,.csv,.txt,.md" multiple onchange="handleDocUpload(${job.job_id}, this.files)">
                <div style="color: var(--text-tertiary); font-size: 13px;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                    Drop files here or click to upload
                    <div style="font-size: 11px; margin-top: 4px; color: var(--text-disabled);">PDF, Excel, CSV, or TXT &middot; Max 20 MB</div>
                </div>
            </div>

            <!-- Doc type selector (shown during upload) -->
            <div id="docTypeSelector" style="display: none; margin-top: 12px;">
                <label class="form-label">Document Type</label>
                <select id="docTypeSelect" class="form-input" style="max-width: 250px;">
                    <option value="change_order">Change Order Log</option>
                    <option value="production_kpi">Production / KPI Tracking</option>
                    <option value="rfi_submittal">RFI / Submittal Log</option>
                    <option value="material_tracking">Material Tracking</option>
                    <option value="other">Other</option>
                </select>
            </div>

            <!-- Document list -->
            <div class="doc-list" id="docList"></div>
        </div>

        <!-- Job-Level PM Context Form -->
        <div class="card" style="margin-bottom: 24px;">
            <div class="card-header">
                <div class="card-title">Job-Level Context ${pm.source ? sourceBadge(pm.source) : ''}</div>
                <span class="save-indicator" id="jobSaveIndicator">
                    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                    Saved
                </span>
            </div>
            <div class="card-body">
                <div class="form-group">
                    <label class="form-label">Your Name</label>
                    <input type="text" class="form-input" id="pm_name" placeholder="e.g., Mike Johnson"
                        value="${pm.pm_name || ''}" onblur="saveJobContext(${job.job_id})">
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                    <div class="form-group">
                        <label class="form-label">Project Summary</label>
                        <textarea class="form-textarea" id="project_summary" placeholder="What was this job? 2-3 sentences."
                            onblur="saveJobContext(${job.job_id})">${pm.project_summary || ''}</textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Site Conditions</label>
                        <textarea class="form-textarea" id="site_conditions" placeholder="Access, terrain, weather, restrictions..."
                            onblur="saveJobContext(${job.job_id})">${pm.site_conditions || ''}</textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Key Challenges</label>
                        <textarea class="form-textarea" id="key_challenges" placeholder="What made this job hard?"
                            onblur="saveJobContext(${job.job_id})">${pm.key_challenges || ''}</textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Key Successes</label>
                        <textarea class="form-textarea" id="key_successes" placeholder="What went well?"
                            onblur="saveJobContext(${job.job_id})">${pm.key_successes || ''}</textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Lessons Learned</label>
                        <textarea class="form-textarea" id="lessons_learned" placeholder="What would you do differently?"
                            onblur="saveJobContext(${job.job_id})">${pm.lessons_learned || ''}</textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">General Notes</label>
                        <textarea class="form-textarea" id="general_notes" placeholder="Anything else relevant..."
                            onblur="saveJobContext(${job.job_id})">${pm.general_notes || ''}</textarea>
                    </div>
                </div>
            </div>
        </div>

        <!-- Cost Code Walkthrough -->
        <div class="overview-title" style="margin-bottom: 16px;">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--wollam-navy)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
            Cost Code Walkthrough
        </div>

        <div class="interview-layout">
            <!-- Cost Code Sidebar -->
            <div class="interview-sidebar">
                <div class="card" style="position: sticky; top: 0; max-height: calc(100vh - 200px); overflow-y: auto;">
                    <div style="padding: 12px 16px; border-bottom: 1px solid var(--border-default); display: flex; align-items: center; justify-content: space-between;">
                        <div style="font-size: 12px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.04em;">
                            Cost Codes (${codes.length})
                        </div>
                        <button class="btn-icon" onclick="toggleCcSort()" title="Sort ${state.ccSortDir === 'asc' ? 'descending' : 'ascending'}" style="width:24px;height:24px;">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                ${state.ccSortDir === 'asc'
                                    ? '<polyline points="17 11 12 6 7 11"/><line x1="12" y1="18" x2="12" y2="6"/>'
                                    : '<polyline points="7 13 12 18 17 13"/><line x1="12" y1="6" x2="12" y2="18"/>'}
                            </svg>
                        </button>
                    </div>
                    <div class="cc-list" style="padding: 8px;" id="ccList">
                        ${(() => { const maxTc = getCcMaxTimecards(); return sortCostCodes(codes).map(cc => renderCcListItem(cc, maxTc)).join(''); })()}
                    </div>
                </div>
            </div>

            <!-- Cost Code Detail -->
            <div class="interview-main" id="ccDetail">
                ${state.selectedCostCode ? renderCostCodeDetail(codes.find(c => c.code === state.selectedCostCode), job.job_id) : '<div class="empty-state"><p>Select a cost code from the list</p></div>'}
            </div>
        </div>

        <!-- Mark Complete -->
        <div style="text-align: center; padding: 32px 0; border-top: 1px solid var(--border-default); margin-top: 24px;">
            <button class="btn btn-gold" onclick="markComplete(${job.job_id})" style="font-size: 15px; padding: 12px 32px;">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                Mark Interview Complete
            </button>
        </div>
    `;
}

function renderCcListItem(cc, maxTc) {
    const tc = cc.timecard_count || 0;
    const ratio = maxTc > 0 ? tc / maxTc : 0;
    // Opacity from 0.08 (no data) to 1.0 (densest)
    const opacity = tc === 0 ? 0 : Math.max(0.12, ratio);
    const active = state.selectedCostCode === cc.code ? 'active' : '';
    return `<div class="cc-list-item ${active}" onclick="selectCostCode('${cc.code}')" style="border-left: 3px solid rgba(0, 52, 126, ${opacity.toFixed(2)});">
        <span class="cc-list-code">${cc.code}</span>
        <span class="cc-list-desc">${cc.description || ''}</span>
    </div>`;
}

function getCcMaxTimecards() {
    const codes = state.jobDetail?.cost_codes || [];
    return Math.max(1, ...codes.map(cc => cc.timecard_count || 0));
}

function sortCostCodes(codes) {
    const sorted = [...codes];
    sorted.sort((a, b) => {
        const aNum = parseInt(a.code, 10);
        const bNum = parseInt(b.code, 10);
        const aVal = isNaN(aNum) ? a.code : aNum;
        const bVal = isNaN(bNum) ? b.code : bNum;
        if (typeof aVal === 'number' && typeof bVal === 'number') {
            return state.ccSortDir === 'asc' ? aVal - bVal : bVal - aVal;
        }
        const cmp = String(a.code).localeCompare(String(b.code));
        return state.ccSortDir === 'asc' ? cmp : -cmp;
    });
    return sorted;
}

function toggleCcSort() {
    state.ccSortDir = state.ccSortDir === 'asc' ? 'desc' : 'asc';
    const codes = state.jobDetail?.cost_codes;
    if (!codes) return;
    // Re-render just the cost code list
    const listEl = document.getElementById('ccList');
    if (listEl) {
        const maxTc = getCcMaxTimecards();
        listEl.innerHTML = sortCostCodes(codes).map(cc => renderCcListItem(cc, maxTc)).join('');
    }
    // Update arrow icon
    const sortBtn = document.querySelector('.btn-icon[onclick="toggleCcSort()"] svg');
    if (sortBtn) {
        sortBtn.innerHTML = state.ccSortDir === 'asc'
            ? '<polyline points="17 11 12 6 7 11"/><line x1="12" y1="18" x2="12" y2="6"/>'
            : '<polyline points="7 13 12 18 17 13"/><line x1="12" y1="6" x2="12" y2="18"/>';
    }
}

function selectCostCode(code) {
    state.selectedCostCode = code;
    const cc = state.jobDetail.cost_codes.find(c => c.code === code);
    if (!cc) return;

    // Update sidebar active state
    document.querySelectorAll('.cc-list-item').forEach(el => {
        el.classList.toggle('active', el.querySelector('.cc-list-code')?.textContent === code);
    });

    // Render detail
    document.getElementById('ccDetail').innerHTML = renderCostCodeDetail(cc, state.jobDetail.job.job_id);
}

function renderCostCodeDetail(cc, jobId) {
    if (!cc) return '<div class="empty-state"><p>Select a cost code</p></div>';

    const ctx = cc.context || {};
    const cb = cc.crew_breakdown || {};
    const trades = cb.trades || {};
    const equipment = cb.equipment || [];
    const workDays = cc.work_days || 1;

    let crewHtml = '';
    if (Object.keys(trades).length > 0) {
        // Calculate avg workers per day for each trade, filter out fringe (<20% presence)
        const tradeAvgs = Object.entries(trades).map(([trade, info]) => {
            const avgPerDay = info.days / workDays;
            return { trade, avgQty: Math.round(avgPerDay * info.workers * 10) / 10, presence: avgPerDay, days: info.days };
        }).filter(t => t.presence >= 0.2)  // only show trades present 20%+ of the time
          .sort((a, b) => b.avgQty - a.avgQty);

        if (tradeAvgs.length > 0) {
            crewHtml += `<div class="crew-grid">${tradeAvgs.map(t => {
                const qty = t.avgQty >= 1 ? Math.round(t.avgQty) : 1;
                return `<span class="crew-tag"><strong>${qty}</strong> ${t.trade}</span>`;
            }).join('')}</div>`;
        }
    }
    if (equipment.length > 0) {
        // Show equipment present 20%+ of work days, with avg quantity
        const equipAvgs = equipment
            .filter(eq => eq.days / workDays >= 0.2)
            .sort((a, b) => b.days - a.days);
        // Group duplicate descriptions
        const equipGroups = {};
        equipAvgs.forEach(eq => {
            const name = eq.desc || eq.code;
            if (!equipGroups[name]) equipGroups[name] = 0;
            equipGroups[name]++;
        });
        if (Object.keys(equipGroups).length > 0) {
            crewHtml += `<div style="margin-top: 6px;"><div class="form-label">Equipment</div><div class="crew-grid">${
                Object.entries(equipGroups).map(([name, qty]) =>
                    `<span class="crew-tag" style="background: rgba(14,165,233,0.06);">${qty > 1 ? `<strong>${qty}</strong> ` : ''}${name}</span>`
                ).join('')
            }</div></div>`;
        }
    }
    if (!crewHtml) {
        crewHtml = '<span style="color: var(--text-tertiary); font-size: 12px;">No crew data</span>';
    }

    return `
        <div class="card card-animate">
            <div class="card-header">
                <div>
                    <div class="card-title">${cc.code} — ${cc.description || 'No description'}</div>
                    <div style="font-size: 12px; color: var(--text-tertiary); margin-top: 2px;">
                        Unit: ${cc.unit || '—'} &middot; Discipline: ${cc.discipline || 'unmapped'}
                    </div>
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    ${confidenceBadge(cc.confidence)}
                    ${cc.timecard_count ? `<span style="font-size: 11px; color: var(--text-tertiary);">${cc.timecard_count} timecards</span>` : ''}
                    <span class="save-indicator" id="ccSaveIndicator">
                        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                        Saved
                    </span>
                </div>
            </div>
            <div class="card-body">
                <!-- Raw Data Display -->
                <div class="data-grid" style="margin-bottom: 20px;">
                    <div class="data-item">
                        <div class="data-item-label">Actual MH/Unit</div>
                        <div class="data-item-value hero">${fmtRate(cc.act_mh_per_unit)}</div>
                    </div>
                    <div class="data-item">
                        <div class="data-item-label">Actual Qty</div>
                        <div class="data-item-value">${fmt(cc.act_qty)} <span style="font-size: 11px; color: var(--text-tertiary);">${cc.unit || ''}</span></div>
                    </div>
                    <div class="data-item">
                        <div class="data-item-label">Actual Hours</div>
                        <div class="data-item-value">${fmt(cc.act_labor_hrs)}</div>
                    </div>
                    <div class="data-item">
                        <div class="data-item-label">Budget Qty</div>
                        <div class="data-item-value">${fmt(cc.bgt_qty)} <span style="font-size: 11px; color: var(--text-tertiary);">${cc.unit || ''}</span></div>
                    </div>
                    <div class="data-item">
                        <div class="data-item-label">Budget Hours</div>
                        <div class="data-item-value">${fmt(cc.bgt_labor_hrs)}</div>
                    </div>
                    <div class="data-item">
                        <div class="data-item-label">Avg Daily Crew</div>
                        <div class="data-item-value">${cc.crew_size_avg ? fmt(cc.crew_size_avg, 1) : '—'}</div>
                    </div>
                </div>

                <!-- Cost Comparison Table (Cost Code Level) -->
                ${(() => {
                    const rc = state.recastCosts && state.recastCosts.cost_codes[cc.code];
                    const hasAny = cc.bgt_total || cc.act_total || (rc && rc.total_cost > 0);
                    if (!hasAny) return '';

                    const actCostPerUnit = (cc.act_qty && cc.act_qty > 0 && cc.act_total) ? cc.act_total / cc.act_qty : null;
                    const rcCostPerUnit = (rc && cc.act_qty && cc.act_qty > 0) ? rc.total_cost / cc.act_qty : null;

                    return `
                <table class="cost-comparison-table" style="margin-bottom: 16px;">
                    <thead>
                        <tr>
                            <th></th>
                            <th>Labor</th>
                            <th>Equipment</th>
                            <th>Material</th>
                            <th>Subs</th>
                            <th>Total</th>
                            <th>$/Unit</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${cc.bgt_total ? `
                        <tr class="cost-row-budget">
                            <td class="cost-row-label">Budget</td>
                            <td>$${fmt(cc.bgt_labor_cost)}</td>
                            <td>$${fmt(cc.bgt_equip_cost)}</td>
                            <td>$${fmt(cc.bgt_matl_cost)}</td>
                            <td>$${fmt(cc.bgt_sub_cost)}</td>
                            <td class="cost-row-total">$${fmt(cc.bgt_total)}</td>
                            <td>${cc.bgt_qty > 0 ? '$' + fmtRate(cc.bgt_total / cc.bgt_qty) : '—'}</td>
                        </tr>` : ''}
                        ${cc.act_total ? `
                        <tr class="cost-row-actual">
                            <td class="cost-row-label"><span class="cost-dot cost-dot-actual"></span>Actual</td>
                            <td>$${fmt(cc.act_labor_cost)}</td>
                            <td>$${fmt(cc.act_equip_cost)}</td>
                            <td>$${fmt(cc.act_matl_cost)}</td>
                            <td>$${fmt(cc.act_sub_cost)}</td>
                            <td class="cost-row-total">$${fmt(cc.act_total)}</td>
                            <td class="cost-row-total" style="color: #10B981;">${actCostPerUnit !== null ? '$' + fmtRate(actCostPerUnit) : '—'}</td>
                        </tr>` : ''}
                        ${rc && rc.total_cost > 0 ? `
                        <tr class="cost-row-recast">
                            <td class="cost-row-label"><span class="cost-dot cost-dot-recast"></span>Recast <span class="cost-row-hint">2026</span></td>
                            <td>$${fmt(rc.labor_cost)}</td>
                            <td>$${fmt(rc.equip_cost)}</td>
                            <td class="cost-cell-na">--</td>
                            <td class="cost-cell-na">--</td>
                            <td class="cost-row-total">$${fmt(rc.total_cost)}</td>
                            <td class="cost-row-total" style="color: #E67E22;">${rcCostPerUnit !== null ? '$' + fmtRate(rcCostPerUnit) : '—'}</td>
                        </tr>` : ''}
                    </tbody>
                </table>`;
                })()}

                <!-- Crew Breakdown -->
                <div style="margin-bottom: 20px;">
                    <div class="form-label">Crew Breakdown</div>
                    ${crewHtml}
                </div>

                ${cc.daily_qty_avg ? `
                <div class="data-grid" style="grid-template-columns: repeat(2, 1fr); margin-bottom: 20px;">
                    <div class="data-item">
                        <div class="data-item-label">Avg Daily Production</div>
                        <div class="data-item-value">${fmt(cc.daily_qty_avg, 1)} <span style="font-size: 11px; color: var(--text-tertiary);">${cc.unit || ''}/day</span></div>
                    </div>
                    <div class="data-item">
                        <div class="data-item-label">Peak Daily Production</div>
                        <div class="data-item-value">${fmt(cc.daily_qty_peak, 1)} <span style="font-size: 11px; color: var(--text-tertiary);">${cc.unit || ''}/day</span></div>
                    </div>
                </div>
                ` : ''}

                <hr style="border: none; border-top: 1px solid var(--border-default); margin: 20px 0;">

                <!-- PM Context Form -->
                <div style="font-size: 14px; font-weight: 600; color: var(--text-primary); margin-bottom: 16px;">
                    PM Context ${ctx.source ? sourceBadge(ctx.source) : ''}
                    <span style="font-size: 11px; font-weight: 400; color: var(--text-tertiary); margin-left: 8px;">All fields optional — auto-saves on blur</span>
                </div>

                <div class="form-group">
                    <label class="form-label">What does this code actually cover?</label>
                    <textarea class="form-textarea" id="cc_scope_included"
                        placeholder="e.g., Forming and stripping walls 20-30' height, one-sided pours against excavation, EFCO forms"
                        onblur="saveCCContext(${jobId}, '${cc.code}')">${ctx.scope_included || ''}</textarea>
                </div>

                <div class="form-group">
                    <label class="form-label">What is NOT included in this code?</label>
                    <textarea class="form-textarea" id="cc_scope_excluded"
                        placeholder="e.g., Rebar is separate (code 2220), concrete placement is separate (code 2230)"
                        onblur="saveCCContext(${jobId}, '${cc.code}')">${ctx.scope_excluded || ''}</textarea>
                </div>

                <div class="form-group">
                    <label class="form-label">Related Cost Codes</label>
                    <input type="text" class="form-input" id="cc_related_codes"
                        placeholder="e.g., 2220, 2230"
                        value="${ctx.related_codes || ''}"
                        onblur="saveCCContext(${jobId}, '${cc.code}')">
                </div>

                <div class="form-group">
                    <label class="form-label">What conditions affected production?</label>
                    <textarea class="form-textarea" id="cc_conditions"
                        placeholder="e.g., Mine site access restrictions added 30 min/day for badging. Winter months required heat blankets."
                        onblur="saveCCContext(${jobId}, '${cc.code}')">${ctx.conditions || ''}</textarea>
                </div>

                <div class="form-group">
                    <label class="form-label">Anything else an estimator should know?</label>
                    <textarea class="form-textarea" id="cc_notes"
                        placeholder="e.g., This rate is conservative — crew was still learning the form system for the first 2 weeks."
                        onblur="saveCCContext(${jobId}, '${cc.code}')">${ctx.notes || ''}</textarea>
                </div>
            </div>
        </div>
    `;
}

// ── Save Handlers ──
async function saveJobContext(jobId) {
    const data = {
        pm_name: document.getElementById('pm_name')?.value || null,
        project_summary: document.getElementById('project_summary')?.value || null,
        site_conditions: document.getElementById('site_conditions')?.value || null,
        key_challenges: document.getElementById('key_challenges')?.value || null,
        key_successes: document.getElementById('key_successes')?.value || null,
        lessons_learned: document.getElementById('lessons_learned')?.value || null,
        general_notes: document.getElementById('general_notes')?.value || null,
    };

    // Skip if all fields are empty
    if (Object.values(data).every(v => !v)) return;

    try {
        await api('/interview/context', {
            method: 'POST',
            body: JSON.stringify({ job_id: jobId, type: 'job', data }),
        });
        showSaveIndicator('jobSaveIndicator');
    } catch (err) {
        console.error('Save failed:', err);
    }
}

async function saveCCContext(jobId, costCode) {
    const data = {
        scope_included: document.getElementById('cc_scope_included')?.value || null,
        scope_excluded: document.getElementById('cc_scope_excluded')?.value || null,
        related_codes: document.getElementById('cc_related_codes')?.value || null,
        conditions: document.getElementById('cc_conditions')?.value || null,
        notes: document.getElementById('cc_notes')?.value || null,
    };

    // Skip if all empty
    if (Object.values(data).every(v => !v)) return;

    try {
        await api('/interview/context', {
            method: 'POST',
            body: JSON.stringify({ job_id: jobId, type: 'cost_code', cost_code: costCode, data }),
        });
        showSaveIndicator('ccSaveIndicator');

        // Update the dot in the sidebar
        const cc = state.jobDetail.cost_codes.find(c => c.code === costCode);
        if (cc) {
            cc.has_context = true;
            cc.context = data;
        }
        // Update dot color
        const listItems = document.querySelectorAll('.cc-list-item');
        listItems.forEach(item => {
            if (item.querySelector('.cc-list-code')?.textContent === costCode) {
                const dot = item.querySelector('.cc-dot');
                if (dot) {
                    dot.classList.remove('no-context');
                    dot.classList.add('has-context');
                }
            }
        });
    } catch (err) {
        console.error('Save failed:', err);
    }
}

function showSaveIndicator(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.add('visible');
    setTimeout(() => el.classList.remove('visible'), 2000);
}

async function markComplete(jobId) {
    try {
        await api(`/interview/complete/${jobId}`, { method: 'POST' });
        navigate('interview');
    } catch (err) {
        console.error('Mark complete failed:', err);
    }
}

// ── Diary Helpers ──
function getDiaryStatsHtml(jobs) {
    const withDiary = jobs.filter(j => j.diary_entry_count > 0);
    const totalEntries = withDiary.reduce((s, j) => s + j.diary_entry_count, 0);
    if (withDiary.length === 0) {
        return '<span>No diary data imported yet. Place .txt exports in the Heavy Job Notes folder and click Import.</span>';
    }
    return `
        <span><span class="diary-stat-value">${withDiary.length}</span> jobs with diary data</span>
        <span><span class="diary-stat-value">${fmt(totalEntries)}</span> total entries</span>
    `;
}

async function importDiaries() {
    const btn = document.getElementById('importDiaryBtn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> Importing...';
    }
    try {
        const result = await api('/diary/import', { method: 'POST' });
        // Reload the job list to pick up diary counts
        const [jobs, progress] = await Promise.all([
            api('/interview/jobs'),
            api('/interview/progress'),
        ]);
        state.jobs = jobs;
        renderJobList(jobs, progress);

        // Show result briefly
        const stats = document.getElementById('diaryStats');
        if (stats) {
            const matched = result.jobs_matched || 0;
            const total = result.total_entries || 0;
            stats.innerHTML = `<span style="color: var(--confidence-high); font-weight: 600;">Imported ${fmt(total)} entries across ${matched} jobs</span>`;
        }
    } catch (err) {
        console.error('Diary import failed:', err);
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Import Diary Files';
        }
    }
}

async function synthesizeDiary(jobId) {
    const btn = document.getElementById('synthesizeBtn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> Synthesizing...';
    }
    try {
        const result = await api(`/diary/synthesize/${jobId}`, { method: 'POST' });
        // Reload the job detail to show synthesized context
        await loadJobDetail(jobId);
    } catch (err) {
        console.error('Synthesis failed:', err);
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Synthesize with AI';
        }
    }
}

// ── Document Upload Helpers ──

function initDocUploadArea(jobId) {
    const area = document.getElementById('docUploadArea');
    if (!area) return;

    area.addEventListener('dragover', (e) => {
        e.preventDefault();
        area.classList.add('dragover');
    });
    area.addEventListener('dragleave', () => {
        area.classList.remove('dragover');
    });
    area.addEventListener('drop', (e) => {
        e.preventDefault();
        area.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            handleDocUpload(jobId, e.dataTransfer.files);
        }
    });
}
const DOC_TYPE_LABELS = {
    change_order: 'Change Order',
    production_kpi: 'Production / KPI',
    rfi_submittal: 'RFI / Submittal',
    material_tracking: 'Material Tracking',
    other: 'Other',
};

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

async function loadDocList(jobId) {
    try {
        const docs = await api(`/documents/list/${jobId}`);
        const container = document.getElementById('docList');
        if (!container) return;

        if (!docs || docs.length === 0) {
            container.innerHTML = '';
            return;
        }

        container.innerHTML = docs.map(doc => `
            <div class="doc-item">
                <div class="doc-item-info">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#0284C7" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    <div>
                        <div class="doc-item-name">${doc.filename}</div>
                        <div class="doc-item-meta">
                            <span class="doc-type-badge">${DOC_TYPE_LABELS[doc.doc_type] || doc.doc_type}</span>
                            &middot; ${formatFileSize(doc.file_size)}
                            &middot; ${doc.text_length ? fmt(doc.text_length) + ' chars extracted' : ''}
                            ${doc.extraction_error ? ' &middot; <span style="color: #EF4444;">extraction error</span>' : ''}
                        </div>
                    </div>
                </div>
                <div class="doc-item-actions">
                    ${doc.analyzed ? '<span class="badge-analyzed">Analyzed</span>' : '<span class="badge-pending">Pending</span>'}
                    <button class="btn-icon danger" onclick="deleteDoc(${doc.id}, ${jobId})" title="Delete">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                    </button>
                </div>
            </div>
        `).join('');
    } catch (err) {
        console.error('Failed to load documents:', err);
    }
}

async function handleDocUpload(jobId, files) {
    if (!files || files.length === 0) return;

    const docType = document.getElementById('docTypeSelect')?.value || 'other';
    const uploadArea = document.getElementById('docUploadArea');

    for (const file of files) {
        if (uploadArea) {
            uploadArea.innerHTML = `<div style="color: #0284C7; font-size: 13px;"><span class="spinner" style="border-top-color: #0284C7; border-color: rgba(14,165,233,0.2); border-top-color: #0284C7;"></span> Uploading ${file.name}...</div>`;
        }

        const formData = new FormData();
        formData.append('file', file);
        formData.append('doc_type', docType);

        try {
            const resp = await fetch(`/api/documents/upload/${jobId}`, {
                method: 'POST',
                body: formData,
            });
            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || 'Upload failed');
            }
        } catch (err) {
            console.error('Upload failed:', err);
            alert(`Upload failed for ${file.name}: ${err.message}`);
        }
    }

    // Reset upload area
    if (uploadArea) {
        uploadArea.innerHTML = `
            <input type="file" id="docFileInput" style="display:none" accept=".pdf,.xlsx,.xls,.csv,.txt,.md" multiple onchange="handleDocUpload(${jobId}, this.files)">
            <div style="color: var(--text-tertiary); font-size: 13px;">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                Drop files here or click to upload
                <div style="font-size: 11px; margin-top: 4px; color: var(--text-disabled);">PDF, Excel, CSV, or TXT &middot; Max 20 MB</div>
            </div>`;
    }

    // Show the enrich button if it wasn't there
    const enrichBtn = document.getElementById('enrichBtn');
    if (!enrichBtn) {
        const docHeader = document.querySelector('.doc-header > div:last-child');
        if (docHeader) {
            docHeader.innerHTML = `
                <button class="btn btn-sm" id="enrichBtn" onclick="enrichFromDocs(${jobId})"
                    style="background: rgba(14,165,233,0.1); color: #0284C7; border-color: rgba(14,165,233,0.3);">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                    Enrich with AI
                </button>`;
        }
    }

    // Reload document list
    await loadDocList(jobId);

    // Reset file input
    const fileInput = document.getElementById('docFileInput');
    if (fileInput) fileInput.value = '';
}

async function deleteDoc(docId, jobId) {
    try {
        await api(`/documents/${docId}`, { method: 'DELETE' });
        await loadDocList(jobId);
    } catch (err) {
        console.error('Delete failed:', err);
    }
}

async function enrichFromDocs(jobId) {
    const btn = document.getElementById('enrichBtn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner" style="border-top-color: #0284C7; border-color: rgba(14,165,233,0.2); border-top-color: #0284C7;"></span> Enriching...';
    }
    try {
        const result = await api(`/documents/enrich/${jobId}`, { method: 'POST' });
        // Reload the full job detail to show enriched context
        await loadJobDetail(jobId);
    } catch (err) {
        console.error('Enrichment failed:', err);
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> Enrich with AI`;
        }
    }
}

function sourceBadge(source) {
    if (!source) return '';
    if (source === 'ai_synthesized') return '<span class="source-badge source-ai">AI Draft</span>';
    if (source === 'ai_document') return '<span class="source-badge source-document">AI + Docs</span>';
    if (source === 'manual') return '<span class="source-badge source-manual">PM</span>';
    return '';
}

// ── Settings Page ──
async function renderSettings() {
    document.getElementById('pageTitle').textContent = 'Rate Settings';
    document.getElementById('pageSubtitle').textContent = 'Labor & equipment rates for cost recalculation';

    const content = document.getElementById('content');
    content.innerHTML = '<div class="empty-state"><p>Loading rates...</p></div>';

    try {
        const [laborData, groupData, coverage] = await Promise.all([
            api('/settings/labor-rates'),
            api('/settings/equipment-groups'),
            api('/settings/rate-coverage'),
        ]);

        const rates = laborData.rates;
        const groups = groupData.groups;

        content.innerHTML = `
            <div class="settings-page">
                <!-- Import Banner -->
                <div class="settings-banner">
                    <div class="banner-left">
                        <div class="banner-title">Rate Import</div>
                        <div class="banner-subtitle">Import rates from HeavyJob export files (PayClass.txt + EquipmentSetup.txt)</div>
                    </div>
                    <button class="btn btn-primary" onclick="importRates()" id="importBtn">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                        Import / Refresh Rates
                    </button>
                </div>

                <!-- Coverage Summary -->
                <div class="settings-coverage">
                    <div class="coverage-card">
                        <div class="coverage-label">Labor Rate Coverage</div>
                        <div class="coverage-value">${coverage.labor.coverage_pct}%</div>
                        <div class="coverage-detail">${fmt(coverage.labor.mapped_codes)} / ${fmt(coverage.labor.total_codes)} codes mapped &middot; ${fmt(coverage.labor.mapped_hours)} / ${fmt(coverage.labor.total_hours)} hrs</div>
                        ${coverage.unmapped_labor.length > 0 ? `
                        <div class="coverage-unmapped">
                            <strong>Unmapped:</strong> ${coverage.unmapped_labor.map(u => `${u.pay_class_code} (${fmt(u.hours)} hrs)`).join(', ')}
                        </div>` : ''}
                    </div>
                    <div class="coverage-card">
                        <div class="coverage-label">Equipment Rate Coverage</div>
                        <div class="coverage-value">${coverage.equipment.coverage_pct}%</div>
                        <div class="coverage-detail">${fmt(coverage.equipment.mapped_codes)} / ${fmt(coverage.equipment.total_codes)} codes mapped &middot; ${fmt(coverage.equipment.mapped_hours)} / ${fmt(coverage.equipment.total_hours)} hrs</div>
                        ${coverage.unmapped_equipment.length > 0 ? `
                        <div class="coverage-unmapped">
                            <strong>Unmapped (top ${coverage.unmapped_equipment.length}):</strong> ${coverage.unmapped_equipment.slice(0, 10).map(u => `${u.equipment_code} (${fmt(u.hours)} hrs)`).join(', ')}${coverage.unmapped_equipment.length > 10 ? '...' : ''}
                        </div>` : ''}
                    </div>
                </div>

                <!-- Tabs -->
                <div class="settings-tabs">
                    <button class="settings-tab active" onclick="switchSettingsTab('labor', this)">Labor Rates (${rates.length})</button>
                    <button class="settings-tab" onclick="switchSettingsTab('equipment', this)">Equipment Groups (${groups.length})</button>
                </div>

                <!-- Tab Content -->
                <div id="settingsTabContent">
                    ${renderLaborRatesTable(rates)}
                </div>
            </div>
        `;
    } catch (err) {
        content.innerHTML = `<div class="empty-state"><h3>Error</h3><p>${err.message}</p></div>`;
    }
}

function renderLaborRatesTable(rates) {
    return `
        <div class="rates-table-wrap">
            <table class="rates-table">
                <thead>
                    <tr>
                        <th>Pay Class</th>
                        <th>Description</th>
                        <th class="num">Base Rate</th>
                        <th class="num">Tax %</th>
                        <th class="num">Fringe</th>
                        <th class="num">Loaded Rate</th>
                        <th class="num">T&M Rate</th>
                        <th class="num">Actual Hrs</th>
                        <th class="num">Jobs</th>
                        <th>Source</th>
                    </tr>
                </thead>
                <tbody>
                    ${rates.map(r => `
                    <tr>
                        <td><strong>${r.pay_class_code}</strong></td>
                        <td>${r.description || ''}</td>
                        <td class="num">$${fmtRate(r.base_rate)}</td>
                        <td class="num">${fmt(r.tax_pct, 2)}%</td>
                        <td class="num">$${fmtRate(r.fringe_non_ot)}</td>
                        <td class="num" style="font-weight: 700; color: var(--wollam-navy);">$${fmtRate(r.loaded_rate)}</td>
                        <td class="num">${r.tm_rate > 0 ? '$' + fmtRate(r.tm_rate) : '—'}</td>
                        <td class="num">${fmt(r.actual_hours)}</td>
                        <td class="num">${fmt(r.job_count)}</td>
                        <td>${r.source === 'imported' ? '<span class="source-badge source-ai">Imported</span>' : '<span class="source-badge source-manual">Manual</span>'}</td>
                    </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

function renderEquipmentGroupsTable(groups) {
    return `
        <div class="rates-table-wrap">
            <table class="rates-table">
                <thead>
                    <tr>
                        <th>Group</th>
                        <th class="num">Items</th>
                        <th class="num">Avg Rate</th>
                        <th class="num">Min</th>
                        <th class="num">Max</th>
                        <th class="num">Actual Hrs</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
                    ${groups.map(g => `
                    <tr>
                        <td><strong>${g.group_name}</strong></td>
                        <td class="num">${fmt(g.item_count)}</td>
                        <td class="num" style="font-weight: 700; color: var(--wollam-navy);">$${fmtRate(g.avg_rate)}</td>
                        <td class="num">$${fmtRate(g.min_rate)}</td>
                        <td class="num">$${fmtRate(g.max_rate)}</td>
                        <td class="num">${fmt(g.total_actual_hours)}</td>
                        <td><button class="btn btn-sm" onclick="showEquipmentGroup('${g.group_name}')">View Items</button></td>
                    </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

async function switchSettingsTab(tab, btn) {
    document.querySelectorAll('.settings-tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    const tabContent = document.getElementById('settingsTabContent');

    if (tab === 'labor') {
        const data = await api('/settings/labor-rates');
        tabContent.innerHTML = renderLaborRatesTable(data.rates);
    } else {
        const data = await api('/settings/equipment-groups');
        tabContent.innerHTML = renderEquipmentGroupsTable(data.groups);
    }
}

async function showEquipmentGroup(groupName) {
    const tabContent = document.getElementById('settingsTabContent');
    tabContent.innerHTML = '<div class="empty-state" style="padding: 24px;"><p>Loading...</p></div>';

    const data = await api(`/settings/equipment-rates?group=${encodeURIComponent(groupName)}`);
    tabContent.innerHTML = `
        <div style="margin-bottom: 12px;">
            <button class="btn btn-sm" onclick="switchSettingsTab('equipment', document.querySelectorAll('.settings-tab')[1])">
                <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
                Back to Groups
            </button>
            <span style="margin-left: 12px; font-weight: 600;">${groupName}</span>
            <span style="color: var(--text-tertiary); font-size: 13px; margin-left: 8px;">${data.count} items</span>
        </div>
        <div class="rates-table-wrap">
            <table class="rates-table">
                <thead>
                    <tr>
                        <th>Code</th>
                        <th>Description</th>
                        <th class="num">Base Rate</th>
                        <th class="num">2nd Rate</th>
                        <th class="num">Actual Hrs</th>
                        <th class="num">Jobs</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.rates.map(r => `
                    <tr>
                        <td><strong>${r.equipment_code}</strong></td>
                        <td>${r.description || ''}</td>
                        <td class="num" style="font-weight: 600;">$${fmtRate(r.base_rate)}</td>
                        <td class="num">${r.second_rate > 0 ? '$' + fmtRate(r.second_rate) : '—'}</td>
                        <td class="num">${fmt(r.actual_hours)}</td>
                        <td class="num">${fmt(r.job_count)}</td>
                    </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

async function importRates() {
    const btn = document.getElementById('importBtn');
    btn.disabled = true;
    btn.innerHTML = 'Importing...';

    try {
        const result = await api('/settings/import-rates', { method: 'POST' });
        btn.innerHTML = `Imported ${result.labor_rates_imported} labor + ${result.equipment_rates_imported} equipment`;
        btn.style.background = 'var(--success-green)';
        setTimeout(() => renderSettings(), 1500);
    } catch (err) {
        btn.innerHTML = `Error: ${err.message}`;
        btn.style.background = 'var(--danger-red, #ef4444)';
        btn.disabled = false;
    }
}

// ── Chat Page ──
async function renderChat() {
    document.getElementById('pageTitle').textContent = 'AI Estimating Chat';
    document.getElementById('pageSubtitle').textContent = 'Ask questions about historical rates & costs';

    // Load conversations list and data summary in parallel
    const [convos, summary] = await Promise.all([
        api('/chat/conversations').catch(() => []),
        api('/chat/data-summary').catch(() => null),
    ]);
    state.chatConversations = convos;
    state.chatDataSummary = summary;

    // Override content area padding for full-height chat layout
    const contentArea = document.getElementById('contentArea');
    contentArea.style.padding = '0';
    contentArea.style.display = 'flex';

    document.getElementById('content').style.maxWidth = 'none';
    document.getElementById('content').style.margin = '0';
    document.getElementById('content').style.width = '100%';
    document.getElementById('content').style.display = 'flex';
    document.getElementById('content').style.height = '100%';

    document.getElementById('content').innerHTML = `
        <div class="chat-layout">
            <!-- Conversation sidebar -->
            <div class="chat-sidebar">
                <button class="btn btn-primary" style="width:100%; margin-bottom:12px;" onclick="chatNewConversation()">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                    New Conversation
                </button>
                <div class="chat-conv-list" id="chatConvList"></div>
            </div>

            <!-- Main chat area -->
            <div class="chat-main">
                <div class="chat-messages" id="chatMessages"></div>
                <div class="chat-input-area">
                    <div class="chat-input-wrap">
                        <textarea id="chatInput" class="chat-input" placeholder="Ask about historical rates, crews, production..." rows="1"
                            onkeydown="chatInputKeydown(event)"></textarea>
                        <button class="chat-send-btn" id="chatSendBtn" onclick="chatSend()">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
                        </button>
                    </div>
                    <div class="chat-input-meta">
                        ${summary ? `<span>${fmt(summary.total_jobs)} jobs &middot; ${fmt(summary.total_rate_items)} rate items &middot; ${fmt(summary.total_timecards)} timecards</span>` : ''}
                    </div>
                </div>
            </div>
        </div>
    `;

    renderChatConvList();

    // If we have an active conversation, load it; otherwise show welcome
    if (state.chatConversationId) {
        await chatLoadConversation(state.chatConversationId);
    } else {
        renderChatWelcome();
    }

    // Auto-resize textarea
    const input = document.getElementById('chatInput');
    if (input) {
        input.addEventListener('input', () => {
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 150) + 'px';
        });
    }
}

function renderChatConvList() {
    const el = document.getElementById('chatConvList');
    if (!el) return;
    if (state.chatConversations.length === 0) {
        el.innerHTML = '<div style="padding:12px;font-size:12px;color:var(--text-tertiary);text-align:center;">No conversations yet</div>';
        return;
    }
    el.innerHTML = state.chatConversations.map(c => {
        const active = c.id === state.chatConversationId ? 'active' : '';
        const date = new Date(c.updated_at || c.created_at);
        const dateStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        return `
            <div class="chat-conv-item ${active}" onclick="chatLoadConversation(${c.id})">
                <div class="chat-conv-title">${escHtml(c.title || 'New Conversation')}</div>
                <div class="chat-conv-meta">${dateStr} &middot; ${c.message_count || 0} msgs</div>
                <button class="chat-conv-delete" onclick="event.stopPropagation();chatDeleteConversation(${c.id})" title="Delete">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
            </div>
        `;
    }).join('');
}

function renderChatWelcome() {
    const el = document.getElementById('chatMessages');
    if (!el) return;
    const s = state.chatDataSummary;
    el.innerHTML = `
        <div class="chat-welcome">
            <div class="chat-welcome-icon">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--wollam-navy)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            </div>
            <h2 style="font-size:20px;font-weight:700;color:var(--text-primary);margin-bottom:4px;">Ask WEIS</h2>
            <p style="color:var(--text-secondary);margin-bottom:20px;max-width:500px;">
                Query Wollam's historical field data — real man-hours, crews, production rates, and costs from every project tracked in HeavyJob.
            </p>
            ${s ? `<div class="chat-welcome-stats">
                <div class="chat-welcome-stat"><span class="chat-welcome-stat-value">${fmt(s.total_jobs)}</span><span class="chat-welcome-stat-label">Jobs</span></div>
                <div class="chat-welcome-stat"><span class="chat-welcome-stat-value">${fmt(s.total_rate_items)}</span><span class="chat-welcome-stat-label">Rate Items</span></div>
                <div class="chat-welcome-stat"><span class="chat-welcome-stat-value">${fmt(s.total_timecards)}</span><span class="chat-welcome-stat-label">Timecards</span></div>
                <div class="chat-welcome-stat"><span class="chat-welcome-stat-value">${s.jobs_with_pm_context}</span><span class="chat-welcome-stat-label">PM Context</span></div>
                ${s.total_estimates > 0 ? `<div class="chat-welcome-stat"><span class="chat-welcome-stat-value">${s.total_estimates}</span><span class="chat-welcome-stat-label">Estimates</span></div>` : ''}
            </div>` : ''}
            <div class="chat-suggested">
                <div class="chat-suggested-label">Try asking:</div>
                <div class="chat-suggested-grid">
                    <button class="chat-suggested-btn" onclick="chatSendSuggested(this.textContent)">What are our historical rates for concrete wall forming?</button>
                    <button class="chat-suggested-btn" onclick="chatSendSuggested(this.textContent)">How many hours should I plan for HDPE pipe fusing?</button>
                    <button class="chat-suggested-btn" onclick="chatSendSuggested(this.textContent)">What crew size works best for structural steel erection?</button>
                    <button class="chat-suggested-btn" onclick="chatSendSuggested(this.textContent)">Compare earthwork production across our completed jobs</button>
                </div>
            </div>
        </div>
    `;
}

function renderChatMessages() {
    const el = document.getElementById('chatMessages');
    if (!el) return;
    if (state.chatMessages.length === 0) {
        renderChatWelcome();
        return;
    }
    el.innerHTML = state.chatMessages.map(m => {
        if (m.role === 'user') {
            return `<div class="chat-msg chat-msg-user"><div class="chat-msg-bubble chat-msg-user-bubble">${escHtml(m.content)}</div></div>`;
        }
        // AI message — render markdown-ish content
        const html = renderMarkdown(m.content);
        const sources = m.sources || [];
        let sourcesHtml = '';
        if (sources.length > 0) {
            sourcesHtml = `
                <div class="chat-sources">
                    <div class="chat-sources-label" onclick="this.parentElement.classList.toggle('expanded')">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
                        Sources (${sources.length})
                    </div>
                    <div class="chat-sources-list">
                        ${sources.map(s => `
                            <span class="chat-source-badge badge-${s.source_type === 'estimate' ? 'estimate' : s.source_type === 'raw_actuals' ? 'raw-actuals' : (s.confidence || 'none').toLowerCase()}">
                                ${s.source_type === 'estimate'
                                    ? `&#9670; ${escHtml(s.job_number)} &middot; ESTIMATE &middot; $${s.bid_total ? Number(s.bid_total).toLocaleString() : '?'}`
                                    : `${escHtml(s.job_number)} &middot; ${escHtml(s.cost_code)} &middot; ${(s.confidence || 'N/A').toUpperCase()}`}
                                ${s.has_pm_context ? '<span title="Has PM context" style="margin-left:2px;">&#9679;</span>' : ''}
                            </span>
                        `).join('')}
                    </div>
                </div>
            `;
        }
        return `<div class="chat-msg chat-msg-ai"><div class="chat-msg-bubble chat-msg-ai-bubble">${html}${sourcesHtml}</div></div>`;
    }).join('');

    // Show loading indicator if waiting
    if (state.chatLoading) {
        el.innerHTML += `
            <div class="chat-msg chat-msg-ai">
                <div class="chat-msg-bubble chat-msg-ai-bubble">
                    <div class="chat-loading">
                        <div class="chat-loading-dot"></div>
                        <div class="chat-loading-dot"></div>
                        <div class="chat-loading-dot"></div>
                    </div>
                </div>
            </div>
        `;
    }

    // Scroll to bottom
    el.scrollTop = el.scrollHeight;
}

function renderMarkdown(text) {
    if (!text) return '';
    // Parse tables first (before escaping)
    let html = '';
    const lines = text.split('\n');
    let i = 0;
    while (i < lines.length) {
        // Detect markdown table (line with | characters, followed by separator row)
        if (lines[i].includes('|') && i + 1 < lines.length && /^\|?[\s-:|]+\|/.test(lines[i + 1])) {
            // Parse header
            const headers = lines[i].split('|').map(s => s.trim()).filter(s => s);
            i += 2; // skip header + separator
            const rows = [];
            while (i < lines.length && lines[i].includes('|')) {
                const cells = lines[i].split('|').map(s => s.trim()).filter(s => s);
                rows.push(cells);
                i++;
            }
            html += '<table><thead><tr>' + headers.map(h => `<th>${escHtml(h)}</th>`).join('') + '</tr></thead><tbody>';
            rows.forEach(r => {
                html += '<tr>' + r.map(c => `<td>${escHtml(c).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')}</td>`).join('') + '</tr>';
            });
            html += '</tbody></table>';
            continue;
        }
        html += escHtml(lines[i]) + '\n';
        i++;
    }
    // Headers
    html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
    html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
    // Bold
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Italic
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    // Code blocks
    html = html.replace(/```([\s\S]*?)```/g, '<pre>$1</pre>');
    // Inline code
    html = html.replace(/`(.+?)`/g, '<code style="background:var(--bg-base);padding:1px 4px;border-radius:3px;font-size:11px;">$1</code>');
    // Bullet points
    html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
    // Numbered lists
    html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
    // Line breaks
    html = html.replace(/\n\n/g, '<br>');
    html = html.replace(/\n/g, '<br>');
    return html;
}

function escHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

async function chatSend() {
    const input = document.getElementById('chatInput');
    const message = input?.value?.trim();
    if (!message || state.chatLoading) return;

    input.value = '';
    input.style.height = 'auto';

    // Add user message to state
    state.chatMessages.push({ role: 'user', content: message });
    state.chatLoading = true;
    renderChatMessages();

    try {
        const result = await api('/chat/send', {
            method: 'POST',
            body: JSON.stringify({
                conversation_id: state.chatConversationId,
                message: message,
            }),
        });

        state.chatConversationId = result.conversation_id;
        state.chatMessages.push({
            role: 'assistant',
            content: result.response,
            sources: result.sources || [],
        });

        // Update conversation list
        const convos = await api('/chat/conversations').catch(() => []);
        state.chatConversations = convos;
        renderChatConvList();
    } catch (err) {
        state.chatMessages.push({
            role: 'assistant',
            content: `**Error:** ${err.message || 'Failed to get response. Please try again.'}`,
            sources: [],
        });
    } finally {
        state.chatLoading = false;
        renderChatMessages();
    }
}

function chatSendSuggested(text) {
    const input = document.getElementById('chatInput');
    if (input) input.value = text;
    chatSend();
}

function chatInputKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        chatSend();
    }
}

async function chatLoadConversation(convId) {
    state.chatConversationId = convId;
    try {
        const conv = await api(`/chat/conversations/${convId}`);
        state.chatMessages = (conv.messages || []).map(m => ({
            role: m.role,
            content: m.content,
            sources: m.sources || [],
        }));
    } catch {
        state.chatMessages = [];
    }
    renderChatMessages();
    renderChatConvList();
}

function chatNewConversation() {
    state.chatConversationId = null;
    state.chatMessages = [];
    renderChatMessages();
    renderChatConvList();
    document.getElementById('chatInput')?.focus();
}

async function chatDeleteConversation(convId) {
    try {
        await api(`/chat/conversations/${convId}`, { method: 'DELETE' });
        state.chatConversations = state.chatConversations.filter(c => c.id !== convId);
        if (state.chatConversationId === convId) {
            state.chatConversationId = null;
            state.chatMessages = [];
            renderChatMessages();
        }
        renderChatConvList();
    } catch { /* ignore */ }
}

// ============================================================
// ESTIMATES PAGE — HeavyBid Estimate Insights
// ============================================================

let estList = [];
let estDetail = null;
let estBiditems = [];
let estActivities = [];
let estResources = [];
let estSearchQuery = '';
let estSyncLoading = false;
let estSelectedBidItemId = null;
let estSelectedActivityId = null;
let estExpandedBidItems = new Set();

async function loadEstimateList() {
    document.getElementById('pageTitle').textContent = 'HeavyBid Estimates';
    document.getElementById('pageSubtitle').textContent = 'Browse synced estimate data from HeavyBid';
    const content = document.getElementById('content');
    content.innerHTML = '<div class="empty-state"><p>Loading estimates...</p></div>';

    try {
        estList = await api('/estimates/');
        renderEstimateList();
    } catch (e) {
        content.innerHTML = `<div class="empty-state"><p>Error loading estimates: ${escHtml(e.message)}</p></div>`;
    }
}

function renderEstimateList() {
    const content = document.getElementById('content');
    const totalBid = estList.reduce((s, e) => s + (e.bid_total || 0), 0);
    const totalMH = estList.reduce((s, e) => s + (e.total_manhours || 0), 0);
    const linked = estList.filter(e => e.linked_job_id).length;

    const filtered = estList.filter(e => {
        if (!estSearchQuery) return true;
        const q = estSearchQuery.toLowerCase();
        return (e.code || '').toLowerCase().includes(q) || (e.name || '').toLowerCase().includes(q);
    });

    content.innerHTML = `
        <div class="kpi-row" style="display:flex;gap:16px;margin-bottom:24px;flex-wrap:wrap;">
            <div class="kpi-card" style="flex:1;min-width:180px;background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;">
                <div style="font-size:28px;font-weight:700;color:var(--text-primary);">${estList.length}</div>
                <div style="font-size:13px;color:var(--text-secondary);margin-top:4px;">Total Estimates</div>
            </div>
            <div class="kpi-card" style="flex:1;min-width:180px;background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;">
                <div style="font-size:28px;font-weight:700;color:var(--wollam-blue);">${linked}</div>
                <div style="font-size:13px;color:var(--text-secondary);margin-top:4px;">Linked to HeavyJob</div>
            </div>
            <div class="kpi-card" style="flex:1;min-width:180px;background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;">
                <div style="font-size:28px;font-weight:700;color:var(--text-primary);">$${fmt(totalBid)}</div>
                <div style="font-size:13px;color:var(--text-secondary);margin-top:4px;">Total Bid Value</div>
            </div>
            <div class="kpi-card" style="flex:1;min-width:180px;background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;">
                <div style="font-size:28px;font-weight:700;color:var(--text-primary);">${fmt(totalMH)}</div>
                <div style="font-size:13px;color:var(--text-secondary);margin-top:4px;">Total Manhours</div>
            </div>
        </div>

        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
            <input type="text" placeholder="Search estimates..." value="${escHtml(estSearchQuery)}"
                   oninput="estSearchQuery=this.value;renderEstimateList()"
                   style="padding:8px 14px;border:1px solid var(--border);border-radius:8px;font-size:14px;width:300px;background:var(--bg-card);color:var(--text-primary);">
            <button onclick="openSyncModal()" style="padding:8px 20px;background:var(--wollam-blue);color:white;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:500;">
                ${estSyncLoading ? 'Syncing...' : 'Sync from HeavyBid'}
            </button>
        </div>

        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:16px;">
            ${filtered.length === 0 ? '<div class="empty-state"><p>No estimates found. Use "Sync from HeavyBid" to pull estimate data.</p></div>' : ''}
            ${filtered.map(est => renderEstimateCard(est)).join('')}
        </div>

        <div id="syncModal" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:1000;display:none;align-items:center;justify-content:center;">
            <div style="background:var(--bg-card);border-radius:16px;padding:32px;max-width:600px;width:90%;max-height:80vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,0.3);">
                <div id="syncModalContent">Loading...</div>
            </div>
        </div>
    `;
}

function renderEstimateCard(est) {
    const linkedBadge = est.linked_job_id
        ? `<span style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;background:rgba(37,99,235,0.1);color:var(--wollam-blue);border-radius:6px;font-size:11px;font-weight:600;cursor:pointer;" onclick="event.stopPropagation();navigate('interview',${est.linked_job_id})">HJ ${escHtml(est.hj_job_number || '')} &rarr;</span>`
        : `<span style="padding:2px 8px;background:rgba(156,163,175,0.1);color:var(--text-tertiary);border-radius:6px;font-size:11px;">Unlinked</span>`;

    return `
        <div class="card" onclick="navigate('estimates',${est.estimate_id})" style="background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;cursor:pointer;transition:all 0.15s;">
            <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:12px;">
                <div>
                    <div style="font-size:13px;font-weight:600;color:var(--wollam-blue);">${escHtml(est.code || '')}</div>
                    <div style="font-size:16px;font-weight:600;color:var(--text-primary);margin-top:2px;">${escHtml(est.name || '')}</div>
                </div>
                ${linkedBadge}
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:13px;">
                <div><span style="color:var(--text-tertiary);">Bid Total</span><br><strong>$${fmt(est.bid_total)}</strong></div>
                <div><span style="color:var(--text-tertiary);">Manhours</span><br><strong>${fmt(est.total_manhours)}</strong></div>
                <div><span style="color:var(--text-tertiary);">Items</span><br><strong>${est.biditem_count || 0} bid items</strong></div>
                <div><span style="color:var(--text-tertiary);">Activities</span><br><strong>${est.activity_count || 0} activities</strong></div>
            </div>
            ${est.state || est.estimator ? `<div style="margin-top:10px;font-size:12px;color:var(--text-tertiary);">${est.state ? escHtml(est.state) : ''}${est.state && est.estimator ? ' · ' : ''}${est.estimator ? 'Est: ' + escHtml(est.estimator) : ''}</div>` : ''}
        </div>
    `;
}

// ── Estimate Detail ──

async function loadEstimateDetail(estimateId) {
    document.getElementById('pageTitle').textContent = 'Estimate Detail';
    document.getElementById('pageSubtitle').textContent = 'Loading...';
    const content = document.getElementById('content');
    content.innerHTML = '<div class="empty-state"><p>Loading estimate...</p></div>';

    try {
        const [detail, biditems, activities, resources] = await Promise.all([
            api(`/estimates/${estimateId}`),
            api(`/estimates/${estimateId}/biditems`),
            api(`/estimates/${estimateId}/activities`),
            api(`/estimates/${estimateId}/resources`),
        ]);
        estDetail = detail;
        estBiditems = biditems;
        estActivities = activities;
        estResources = resources;
        renderEstimateDetail();

        // Auto-select first activity
        if (estBiditems.length > 0 && estActivities.length > 0) {
            const firstBi = estBiditems[0];
            const firstAct = estActivities.find(a => a.hcss_biditem_id === firstBi.hcss_bi_id);
            if (firstAct) {
                estExpandedBidItems.add(firstBi.hcss_bi_id);
                selectEstActivity(firstBi.hcss_bi_id, firstAct.hcss_act_id);
            }
        }
    } catch (e) {
        content.innerHTML = `<div class="empty-state"><p>Error: ${escHtml(e.message)}</p></div>`;
    }
}

function renderEstimateDetail() {
    const d = estDetail;
    document.getElementById('pageTitle').textContent = `${d.code || ''} — ${d.name || ''}`;
    document.getElementById('pageSubtitle').textContent = `HeavyBid Estimate · ${estBiditems.length} bid items · ${estActivities.length} activities · ${estResources.length} resources`;

    const content = document.getElementById('content');

    // Cross-link button
    const crossLink = d.linked_job_id
        ? `<button onclick="navigate('interview',${d.linked_job_id})" style="padding:8px 20px;background:var(--wollam-blue);color:white;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:500;">View Actuals &rarr;</button>`
        : '';

    content.innerHTML = `
        <div style="margin-bottom:24px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
                <button onclick="navigate('estimates')" style="padding:6px 16px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;cursor:pointer;font-size:13px;color:var(--text-secondary);">&larr; Back to Estimates</button>
                ${crossLink}
            </div>
            ${d.linked_job_id ? `<div style="margin-bottom:12px;padding:8px 14px;background:rgba(37,99,235,0.05);border:1px solid rgba(37,99,235,0.15);border-radius:8px;font-size:13px;color:var(--wollam-blue);">Linked to HeavyJob: <strong>${escHtml(d.hj_job_number || '')} — ${escHtml(d.hj_job_name || '')}</strong> (${escHtml(d.hj_job_status || '')})</div>` : ''}
        </div>

        <!-- KPI Bar -->
        <div style="display:flex;gap:12px;margin-bottom:24px;flex-wrap:wrap;">
            ${estKpi('Bid Total', '$' + fmt(d.bid_total))}
            ${estKpi('Labor', '$' + fmt(d.total_labor))}
            ${estKpi('Burden', '$' + fmt(d.total_burden))}
            ${estKpi('Equipment', '$' + fmt(d.total_equip))}
            ${estKpi('Material', '$' + fmt(d.total_perm_material))}
            ${estKpi('Subs', '$' + fmt(d.total_subcontract))}
            ${estKpi('Markup', '$' + fmt(d.actual_markup))}
            ${estKpi('Manhours', fmt(d.total_manhours))}
        </div>

        <!-- Master-Detail Layout -->
        <div class="interview-layout">
            <!-- Left: Bid Item / Activity Tree -->
            <div class="interview-sidebar">
                <div class="card" style="position:sticky;top:0;max-height:calc(100vh - 200px);overflow-y:auto;">
                    <div style="padding:12px 16px;border-bottom:1px solid var(--border-default);">
                        <div style="font-size:12px;font-weight:600;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.04em;">
                            Bid Items (${estBiditems.length}) &middot; Activities (${estActivities.length})
                        </div>
                    </div>
                    <div class="cc-list" style="padding:8px;" id="estTree">
                        ${renderEstTree()}
                    </div>
                </div>
            </div>

            <!-- Right: Activity Detail -->
            <div class="interview-main" id="estActivityDetail">
                <div class="empty-state"><p>Select an activity from the list</p></div>
            </div>
        </div>
    `;
}

function estKpi(label, value) {
    return `<div style="flex:1;min-width:120px;background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:14px 16px;">
        <div style="font-size:18px;font-weight:700;color:var(--text-primary);">${value}</div>
        <div style="font-size:12px;color:var(--text-secondary);margin-top:2px;">${label}</div>
    </div>`;
}

// ── Estimate Tree Sidebar ──

function renderEstTree() {
    const maxBiMH = Math.max(1, ...estBiditems.map(bi => bi.manhours || 0));
    const maxActMH = Math.max(1, ...estActivities.map(a => a.man_hours || 0));

    return estBiditems.map(bi => {
        const biCode = (bi.biditem_code || '').trim();
        const isExpanded = estExpandedBidItems.has(bi.hcss_bi_id);
        const biOpacity = bi.manhours ? Math.max(0.12, (bi.manhours || 0) / maxBiMH) : 0;
        const acts = estActivities.filter(a => a.hcss_biditem_id === bi.hcss_bi_id);
        const chevron = isExpanded ? '&#9662;' : '&#9656;';

        let html = `<div class="cc-list-item est-tree-bi" onclick="toggleEstBidItem('${bi.hcss_bi_id}')" style="border-left:3px solid rgba(0,52,126,${biOpacity.toFixed(2)});">
            <span class="cc-list-code">${escHtml(biCode)}</span>
            <span class="cc-list-desc">${escHtml(bi.description || '')}</span>
            <span class="est-tree-chevron">${chevron}</span>
        </div>`;

        if (isExpanded) {
            html += acts.map(act => {
                const actOpacity = act.man_hours ? Math.max(0.12, (act.man_hours || 0) / maxActMH) : 0;
                const isActive = estSelectedActivityId === act.hcss_act_id;
                return `<div class="cc-list-item est-tree-act ${isActive ? 'active' : ''}" onclick="event.stopPropagation();selectEstActivity('${bi.hcss_bi_id}','${act.hcss_act_id}')" style="border-left:3px solid rgba(252,185,0,${actOpacity.toFixed(2)});">
                    <span class="cc-list-code">${escHtml(act.activity_code || '')}</span>
                    <span class="cc-list-desc">${escHtml(act.description || '')}</span>
                </div>`;
            }).join('');

            if (acts.length === 0) {
                html += `<div style="padding:6px 28px;font-size:12px;color:var(--text-tertiary);font-style:italic;">No activities</div>`;
            }
        }

        return html;
    }).join('');
}

function toggleEstBidItem(biId) {
    if (estExpandedBidItems.has(biId)) {
        estExpandedBidItems.delete(biId);
    } else {
        estExpandedBidItems.add(biId);
    }
    const treeEl = document.getElementById('estTree');
    if (treeEl) treeEl.innerHTML = renderEstTree();
}

function selectEstActivity(biId, actId) {
    estSelectedBidItemId = biId;
    estSelectedActivityId = actId;

    // Ensure parent bid item is expanded
    if (!estExpandedBidItems.has(biId)) {
        estExpandedBidItems.add(biId);
    }

    // Re-render tree to update active state
    const treeEl = document.getElementById('estTree');
    if (treeEl) treeEl.innerHTML = renderEstTree();

    // Render detail panel
    const act = estActivities.find(a => a.hcss_act_id === actId);
    const bi = estBiditems.find(b => b.hcss_bi_id === biId);
    const detailEl = document.getElementById('estActivityDetail');
    if (detailEl && act && bi) {
        detailEl.innerHTML = renderEstActivityDetail(act, bi);
    }
}

function renderEstActivityDetail(act, bi) {
    const biCode = (bi.biditem_code || '').trim();
    const res = estResources.filter(r => r.hcss_activity_id === act.hcss_act_id);
    const hasNotes = act.notes && act.notes.trim();

    // Crew counts from resources (sum pieces for labor, count for equipment)
    const crewLabor = res.filter(r => (r.type_cost || '').toUpperCase().trim() === 'L')
        .reduce((sum, r) => sum + (r.pieces || 0), 0);
    const crewEquip = res.filter(r => (r.type_cost || '').toUpperCase().trim() === 'E').length;

    // MH/Unit: production_rate when production_type is MU (manhours per unit)
    const mhPerUnit = act.production_rate || null;

    // Units/Hr: crew_labor / MH/Unit (how many units the full crew produces per hour)
    const unitsPerHr = (mhPerUnit && crewLabor) ? (crewLabor / mhPerUnit) : null;

    // Un/Shift: Units/Hr * hours_per_day
    const unPerShift = (unitsPerHr && act.hours_per_day) ? (unitsPerHr * act.hours_per_day) : null;

    // Crew$/Unit: crew_cost / quantity (NOT direct_total)
    const crewCostPerUnit = (act.crew_cost && act.quantity) ? (act.crew_cost / act.quantity) : null;

    // Shifts: manhours / (crew_labor * hours_per_day)
    const shifts = (act.man_hours && crewLabor && act.hours_per_day)
        ? (act.man_hours / (crewLabor * act.hours_per_day)) : null;

    // Unit costs ($/unit) for headers
    const biUnitCost = (bi.total_cost && bi.quantity) ? (bi.total_cost / bi.quantity) : null;
    const actUnitCost = (act.direct_total && act.quantity) ? (act.direct_total / act.quantity) : null;

    return `
        <!-- Parent Bid Item Context -->
        <div class="est-bi-context">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                <div style="font-size:11px;font-weight:600;color:var(--text-tertiary);text-transform:uppercase;letter-spacing:0.04em;">Parent Bid Item</div>
                <div>
                    <span style="font-weight:600;color:var(--wollam-navy);">${escHtml(biCode)}</span>
                    <span style="margin-left:8px;color:var(--text-primary);">${escHtml(bi.description || '')}</span>
                </div>
            </div>
            <div class="est-productivity-grid" style="grid-template-columns:repeat(5,1fr);">
                <div class="est-prod-cell"><span class="est-prod-label">Quantity</span><span class="est-prod-value">${bi.quantity || 0} ${escHtml(bi.units || '')}</span></div>
                <div class="est-prod-cell"><span class="est-prod-label">Cost</span><span class="est-prod-value">$${fmt(bi.total_cost)}</span></div>
                <div class="est-prod-cell"><span class="est-prod-label">Bid</span><span class="est-prod-value">$${fmt(bi.bid_price)}</span></div>
                <div class="est-prod-cell"><span class="est-prod-label">Manhours</span><span class="est-prod-value">${fmt(bi.manhours)}</span></div>
                <div class="est-prod-cell"><span class="est-prod-label">U.Cost</span><span class="est-prod-value" style="color:var(--wollam-navy);">$${biUnitCost != null ? fmt(biUnitCost, 2) : '—'}/${escHtml(bi.units || 'unit')}</span></div>
            </div>
        </div>

        <!-- Activity Detail Card -->
        <div class="card card-animate">
            <div class="card-header">
                <div>
                    <div class="card-title">${escHtml(act.activity_code || '')} — ${escHtml(act.description || '')}</div>
                    <div style="font-size:12px;color:var(--text-tertiary);margin-top:2px;">
                        ${act.quantity || 0} ${escHtml(act.units || '')}
                    </div>
                </div>
                <div style="text-align:right;">
                    <div style="display:flex;align-items:baseline;gap:12px;justify-content:flex-end;">
                        <div style="font-size:18px;font-weight:700;color:var(--text-primary);">$${fmt(act.direct_total)}</div>
                    </div>
                    <div style="font-size:13px;font-weight:700;color:var(--wollam-navy);margin-top:2px;">U.Cost: $${actUnitCost != null ? fmt(actUnitCost, 2) : '—'}/${escHtml(act.units || 'unit')}</div>
                    <div style="font-size:12px;color:var(--text-tertiary);margin-top:1px;">${fmt(act.man_hours)} MH</div>
                </div>
            </div>
            <div class="card-body">

                <!-- Activity Main: Crew + Production + Crew Hrs / Hrs/Shift / Days -->
                <div class="est-activity-main">
                    <div class="est-field"><span class="est-field-label">Crew</span><span class="est-field-value">${escHtml(act.crew || '—')}</span></div>
                    <div class="est-field"><span class="est-field-label">Prod</span><span class="est-field-value">${escHtml(act.production_type || '—')}</span></div>
                    <div class="est-field"><span class="est-field-label">Rate</span><span class="est-field-value">${act.production_rate != null ? fmtRate(act.production_rate) : '—'}</span></div>
                    <div class="est-field"><span class="est-field-label">Crew Hrs</span><span class="est-field-value est-field-highlight">${act.crew_hours != null ? fmtRate(act.crew_hours) : '—'}</span></div>
                    <div class="est-field"><span class="est-field-label">Hrs/Shift</span><span class="est-field-value">${act.hours_per_day != null ? fmtRate(act.hours_per_day) : '—'}</span></div>
                    <div class="est-field"><span class="est-field-label">Days</span><span class="est-field-value">${act.calculated_duration != null ? fmtRate(act.calculated_duration) : '—'}</span></div>
                </div>

                <!-- Activity Productivity Information — mirrors HeavyBid 2x4 grid -->
                <div class="est-productivity-section">
                    <div class="est-productivity-title">Activity Productivity Information</div>
                    <div class="est-productivity-grid">
                        <div class="est-prod-cell"><span class="est-prod-label">Manhours</span><span class="est-prod-value">${act.man_hours != null ? fmt(act.man_hours, 3) : '—'}</span></div>
                        <div class="est-prod-cell"><span class="est-prod-label">Units/Hr</span><span class="est-prod-value">${unitsPerHr != null ? fmt(unitsPerHr, 4) : '—'}</span></div>
                        <div class="est-prod-cell"><span class="est-prod-label">Un/Shift</span><span class="est-prod-value">${unPerShift != null ? fmt(unPerShift, 4) : '—'}</span></div>
                        <div class="est-prod-cell"><span class="est-prod-label">Crew Labor</span><span class="est-prod-value">${crewLabor ? fmt(crewLabor, 2) : '—'}</span></div>

                        <div class="est-prod-cell"><span class="est-prod-label">MH/Unit</span><span class="est-prod-value">${mhPerUnit != null ? fmt(mhPerUnit, 4) : '—'}</span></div>
                        <div class="est-prod-cell"><span class="est-prod-label">Crew$/Unit</span><span class="est-prod-value">${crewCostPerUnit != null ? fmt(crewCostPerUnit, 4) : '—'}</span></div>
                        <div class="est-prod-cell"><span class="est-prod-label">Shifts</span><span class="est-prod-value">${shifts != null ? fmt(shifts, 4) : '—'}</span></div>
                        <div class="est-prod-cell"><span class="est-prod-label">Crew Equip</span><span class="est-prod-value">${crewEquip ? fmt(crewEquip, 2) : '—'}</span></div>
                    </div>
                </div>

                <!-- Cost Breakdown -->
                <div style="margin-bottom:16px;">
                    <div style="font-size:11px;font-weight:600;color:var(--text-tertiary);text-transform:uppercase;letter-spacing:0.04em;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid var(--border-default);">Cost Breakdown</div>
                    <div class="est-productivity-grid" style="grid-template-columns:repeat(6,1fr);">
                        <div class="est-prod-cell"><span class="est-prod-label">Labor</span><span class="est-prod-value">$${fmt(act.labor)}</span></div>
                        <div class="est-prod-cell"><span class="est-prod-label">Burden</span><span class="est-prod-value">$${fmt(act.burden)}</span></div>
                        <div class="est-prod-cell"><span class="est-prod-label">Material</span><span class="est-prod-value">$${fmt(act.perm_material)}</span></div>
                        <div class="est-prod-cell"><span class="est-prod-label">Equip OE</span><span class="est-prod-value">$${fmt(act.equip_oe)}</span></div>
                        <div class="est-prod-cell"><span class="est-prod-label">Co Equip</span><span class="est-prod-value">$${fmt(act.company_equip)}</span></div>
                        <div class="est-prod-cell"><span class="est-prod-label">Subs</span><span class="est-prod-value">$${fmt(act.subcontract)}</span></div>
                    </div>
                </div>

                ${hasNotes ? `
                <!-- Estimator Notes -->
                <div style="margin-bottom:16px;padding:12px 16px;background:rgba(245,158,11,0.06);border-left:3px solid rgba(245,158,11,0.5);border-radius:0 8px 8px 0;font-size:13px;line-height:1.5;color:var(--text-primary);white-space:pre-wrap;">${escHtml(act.notes)}</div>
                ` : ''}

                ${res.length > 0 ? `
                <!-- Resources -->
                <div style="margin-top:8px;">
                    <div style="font-size:12px;font-weight:600;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.04em;margin-bottom:8px;">${res.length} Resources</div>
                    <table style="width:100%;font-size:12px;border-collapse:collapse;">
                        <thead><tr style="border-bottom:1px solid var(--border-default);">
                            <th style="text-align:left;padding:6px 8px;color:var(--text-tertiary);font-weight:500;">Code</th>
                            <th style="text-align:left;padding:6px 8px;color:var(--text-tertiary);font-weight:500;">Description</th>
                            <th style="text-align:left;padding:6px 8px;color:var(--text-tertiary);font-weight:500;">Type</th>
                            <th style="text-align:right;padding:6px 8px;color:var(--text-tertiary);font-weight:500;">Qty</th>
                            <th style="text-align:right;padding:6px 8px;color:var(--text-tertiary);font-weight:500;">Unit Price</th>
                            <th style="text-align:right;padding:6px 8px;color:var(--text-tertiary);font-weight:500;">Total</th>
                        </tr></thead>
                        <tbody>
                            ${res.map(r => {
                                const tc = (r.type_cost || '').toUpperCase().trim();
                                const color = tc === 'L' ? '#22c55e' : (tc === 'E' || tc === 'C') ? '#eab308' : (tc === 'P' || tc === 'M') ? '#00347E' : tc === 'S' ? '#ef4444' : '#94a3b8';
                                return `<tr style="border-bottom:1px solid rgba(0,0,0,0.04);">
                                <td style="padding:6px 8px;font-weight:500;"><span style="display:inline-flex;align-items:center;gap:6px;"><span style="width:10px;height:10px;border-radius:2px;background:${color};flex-shrink:0;"></span>${escHtml(r.resource_code || '')}</span></td>
                                <td style="padding:6px 8px;">${escHtml(r.description || '')}</td>
                                <td style="padding:6px 8px;">${escHtml(r.type_cost || '')}</td>
                                <td style="padding:6px 8px;text-align:right;">${r.quantity || '—'}</td>
                                <td style="padding:6px 8px;text-align:right;">$${fmtRate(r.unit_price)}</td>
                                <td style="padding:6px 8px;text-align:right;">$${fmt(r.total)}</td>
                            </tr>`;
                            }).join('')}
                        </tbody>
                    </table>
                </div>
                ` : '<div style="font-size:12px;color:var(--text-tertiary);font-style:italic;">No resources</div>'}
            </div>
        </div>
    `;
}

// ── Sync Modal ──

async function openSyncModal() {
    const modal = document.getElementById('syncModal');
    const modalContent = document.getElementById('syncModalContent');
    modal.style.display = 'flex';
    modalContent.innerHTML = '<p>Loading available estimates from HeavyBid...</p>';

    try {
        const available = await api('/estimates/available');
        if (available.length === 0) {
            modalContent.innerHTML = '<p>No estimates available in HeavyBid.</p><button onclick="closeSyncModal()" style="margin-top:16px;padding:8px 20px;background:var(--border);border:none;border-radius:8px;cursor:pointer;">Close</button>';
            return;
        }

        const syncedIds = new Set(available.filter(e => e.already_synced).map(e => e.hcss_est_id));
        const newEstimates = available.filter(e => !e.already_synced);

        modalContent.innerHTML = `
            <h3 style="margin-bottom:16px;font-size:18px;font-weight:600;">Sync Estimates from HeavyBid</h3>
            <p style="font-size:13px;color:var(--text-secondary);margin-bottom:16px;">${available.length} estimates available, ${syncedIds.size} already synced</p>
            <div style="max-height:400px;overflow-y:auto;">
                ${available.map(e => `
                    <label style="display:flex;align-items:center;gap:10px;padding:10px;border-bottom:1px solid var(--border);cursor:${e.already_synced ? 'default' : 'pointer'};">
                        <input type="checkbox" value="${e.hcss_est_id}" ${e.already_synced ? 'checked disabled' : ''} class="sync-checkbox">
                        <div style="flex:1;">
                            <div style="font-weight:600;font-size:14px;">${escHtml(e.code || '?')}</div>
                            <div style="font-size:12px;color:var(--text-secondary);">${escHtml(e.name || '')} · $${fmt(e.bid_total)} · ${fmt(e.total_manhours)} MH</div>
                        </div>
                        ${e.already_synced ? '<span style="font-size:11px;color:var(--text-tertiary);">Synced</span>' : '<span style="font-size:11px;color:var(--wollam-blue);">New</span>'}
                    </label>
                `).join('')}
            </div>
            <div style="display:flex;gap:12px;margin-top:20px;justify-content:flex-end;">
                <button onclick="closeSyncModal()" style="padding:8px 20px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;cursor:pointer;">Cancel</button>
                <button id="syncBtn" onclick="runSync()" style="padding:8px 20px;background:var(--wollam-blue);color:white;border:none;border-radius:8px;cursor:pointer;font-weight:500;">Sync Selected</button>
            </div>
        `;
    } catch (e) {
        modalContent.innerHTML = `<p>Error: ${escHtml(e.message)}</p><button onclick="closeSyncModal()" style="margin-top:16px;padding:8px 20px;background:var(--border);border:none;border-radius:8px;cursor:pointer;">Close</button>`;
    }
}

function closeSyncModal() {
    document.getElementById('syncModal').style.display = 'none';
}

async function runSync() {
    const checkboxes = document.querySelectorAll('.sync-checkbox:checked:not(:disabled)');
    const ids = Array.from(checkboxes).map(cb => cb.value);
    if (ids.length === 0) {
        alert('Select at least one estimate to sync.');
        return;
    }

    const btn = document.getElementById('syncBtn');
    btn.textContent = 'Syncing...';
    btn.disabled = true;

    try {
        const result = await api('/estimates/sync', {
            method: 'POST',
            body: JSON.stringify({ estimate_ids: ids }),
        });
        closeSyncModal();
        loadEstimateList();
    } catch (e) {
        btn.textContent = 'Error — retry';
        btn.disabled = false;
    }
}

// ── Init ──
document.addEventListener('DOMContentLoaded', () => {
    navigate('interview');
});
