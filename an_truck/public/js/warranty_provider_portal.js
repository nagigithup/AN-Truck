(() => {
	"use strict";
	const API = "an_truck.warranty.portal_api.";
	const boot = window.warrantyPortalBootstrap || {};
	let activeClaim = null;
	let parts = [];
	let services = [];

	const $ = (selector, root = document) => root.querySelector(selector);
	const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
	const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
	const dateText = (value) => value ? String(value).slice(0, 10) : "—";
	const money = (value, currency = "") => `${Number(value || 0).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})} ${esc(currency)}`;

	async function call(method, args = {}, type = "GET") {
		try {
			const response = await frappe.call({method: API + method, args, type, freeze: type === "POST"});
			return response.message;
		} catch (error) {
			const message = error?.message || error?.exc_type || "The request could not be completed.";
			showAlert(message.replace(/<[^>]*>/g, ""));
			throw error;
		}
	}

	function showAlert(message) {
		const alert = $("#wp-alert");
		alert.textContent = message;
		alert.hidden = false;
		window.scrollTo({top: 0, behavior: "smooth"});
	}
	function clearAlert() { $("#wp-alert").hidden = true; }

	function showView(name) {
		clearAlert();
		$$(`.wp-view`).forEach((node) => { node.hidden = node.id !== `view-${name}`; });
		$$(`.wp-tabs button`).forEach((button) => button.classList.toggle("active", button.dataset.view === name));
		if (name === "dashboard") loadDashboard();
		if (name === "claims") loadClaims();
	}

	async function loadDashboard() {
		const data = await call("get_dashboard");
		const statuses = Object.entries(data.counts || {});
		$("#wp-counts").innerHTML = statuses.length
			? statuses.map(([label, count]) => `<div class="wp-stat"><strong>${Number(count)}</strong><span>${esc(label)}</span></div>`).join("")
			: `<div class="wp-stat"><strong>0</strong><span>No claims yet</span></div>`;
		$("#wp-recent").innerHTML = claimTable(data.recent_claims || []);
		bindClaimRows($("#wp-recent"));
	}

	async function loadClaims() {
		const data = await call("list_claims", {page_length: 50});
		$("#wp-claims").innerHTML = claimTable(data.claims || []);
		bindClaimRows($("#wp-claims"));
	}

	function claimTable(rows) {
		if (!rows.length) return `<p>No warranty claims are available.</p>`;
		return `<table class="wp-table"><thead><tr><th>Claim</th><th>VIN</th><th>Status</th><th>Branch</th><th>Updated</th></tr></thead><tbody>${rows.map((row) => `
			<tr data-claim="${esc(row.name)}"><td>${esc(row.name)}</td><td>${esc(row.vin || row.serial_no)}</td><td><span class="wp-badge">${esc(row.status || row.custom_claim_status)}</span></td><td>${esc(row.branch || row.custom_warranty_provider_branch || "—")}</td><td>${dateText(row.modified)}</td></tr>`).join("")}</tbody></table>`;
	}

	function bindClaimRows(root) {
		$$(`[data-claim]`, root).forEach((row) => row.addEventListener("click", () => openClaim(row.dataset.claim)));
	}

	async function searchVin(event) {
		event.preventDefault();
		const warranty = await call("search_vin", {vin: $("#vin-input").value});
		const covered = (warranty.coverage || []).filter((row) => row.covered);
		$("#warranty-result").innerHTML = `<div class="wp-panel">
			<div class="wp-panel-title"><div><p class="wp-eyebrow">${esc(warranty.vin)}</p><h2>${esc(warranty.vehicle_model || "Vehicle warranty")}</h2></div><span class="wp-badge">${esc(warranty.status)}</span></div>
			<div class="wp-stat-grid"><div class="wp-stat"><strong>${dateText(warranty.start_date)}</strong><span>Warranty start</span></div><div class="wp-stat"><strong>${dateText(warranty.expiry_date)}</strong><span>Warranty expiry</span></div><div class="wp-stat"><strong>${covered.length}</strong><span>Covered categories</span></div></div>
			<p><strong>Customer:</strong> ${esc(warranty.customer_name || "—")}</p>
			<h3>Coverage</h3><table class="wp-table"><thead><tr><th>Component</th><th>Coverage</th><th>Description</th></tr></thead><tbody>${(warranty.coverage || []).map((row) => `<tr><td>${esc(row.category)}</td><td>${row.covered ? "Covered" : "Excluded"}</td><td>${esc(row.description || row.exclusions || "—")}</td></tr>`).join("")}</tbody></table>
			<div class="wp-form-actions">${warranty.can_create_claim ? `<button id="create-claim" class="wp-primary">Create claim</button>` : `<span class="wp-badge">New claims unavailable</span>`}</div>
		</div>`;
		if (warranty.can_create_claim) $("#create-claim").addEventListener("click", () => openCreateDialog(warranty));
	}

	function openCreateDialog(warranty) {
		const dialog = $("#create-claim-dialog");
		const form = $("#create-claim-form");
		form.reset();
		form.elements.vehicle_warranty.value = warranty.name;
		form.elements.custom_failure_date.value = new Date().toISOString().slice(0, 10);
		const select = form.elements.branch;
		select.innerHTML = (warranty.branches || []).map((branch) => `<option value="${esc(branch.name)}">${esc(branch.branch_name)}${branch.city ? ` — ${esc(branch.city)}` : ""}</option>`).join("");
		$("#create-branch-label").hidden = boot.branch_mode === "fixed";
		dialog.showModal();
	}

	async function createClaim(event) {
		event.preventDefault();
		const form = event.currentTarget;
		const claim = await call("create_claim", {
			vehicle_warranty: form.elements.vehicle_warranty.value,
			complaint: form.elements.complaint.value,
			branch: form.elements.branch.value,
			payload: JSON.stringify({custom_failure_date: form.elements.custom_failure_date.value}),
		}, "POST");
		$("#create-claim-dialog").close();
		await renderClaim(claim);
	}

	async function openClaim(name) { await renderClaim(await call("get_claim", {name})); }

	async function renderClaim(claim) {
		activeClaim = claim;
		parts = (claim.parts || []).map((row) => ({...row}));
		services = (claim.services || []).map((row) => ({...row}));
		showView("claim");
		$("#claim-title").textContent = claim.name;
		$("#claim-meta").innerHTML = `<span class="wp-badge">${esc(claim.status)}</span><span>VIN ${esc(claim.vin)}</span><span>Branch ${esc(claim.branch)}</span>`;
		const form = $("#claim-form");
		const values = {
			complaint: claim.complaint, custom_failure_date: claim.failure_date,
			custom_current_odometer: claim.current_odometer || "", custom_inspection_date: claim.inspection?.date,
			custom_technician_name: claim.inspection?.technician, custom_diagnosis: claim.inspection?.diagnosis,
			custom_inspection_details: claim.inspection?.details, custom_root_cause: claim.inspection?.root_cause,
			custom_provider_recommendation: claim.assessment?.recommendation, custom_provider_reason: claim.assessment?.reason,
			custom_provider_technical_notes: claim.assessment?.technical_notes,
			custom_other_charges: claim.cost_summary?.other_charges || "", custom_other_covered_amount: claim.cost_summary?.other_covered_amount || "",
		};
		Object.entries(values).forEach(([name, value]) => { if (form.elements[name]) form.elements[name].value = value ?? ""; });
		renderRows();
		renderDocuments(claim.documents || []);
		renderCosts(claim.cost_summary || {});
		$("#claim-actions").innerHTML = (claim.allowed_actions || []).map((action) => `<button type="button" class="wp-primary" data-action="${esc(action)}">${esc(action)}</button>`).join(" ");
		$$(`[data-action]`, $("#claim-actions")).forEach((button) => button.addEventListener("click", () => runAction(button.dataset.action)));
		$$(`input,textarea,select,button`, form).forEach((field) => { if (!field.closest(".wp-upload")) field.disabled = !claim.editable; });
		$("#upload-document").disabled = !claim.editable;
	}

	function renderRows() {
		$("#parts-table").innerHTML = parts.length ? parts.map((row, index) => rowEditor(row, index, "part")).join("") : `<p>No parts added.</p>`;
		$("#services-table").innerHTML = services.length ? services.map((row, index) => rowEditor(row, index, "service")).join("") : `<p>No services added.</p>`;
		$$(`[data-row-type]`).forEach((input) => input.addEventListener("change", updateRow));
		$$(`[data-remove-row]`).forEach((button) => button.addEventListener("click", removeRow));
	}

	function rowEditor(row, index, type) {
		const service = type === "service";
		return `<div class="wp-row-editor ${service ? "service" : ""}">
			<label><span>Coverage category</span><input data-row-type="${type}" data-index="${index}" data-key="coverage_category" value="${esc(row.coverage_category)}"></label>
			<label><span>${service ? "Service / description" : "Part description"}</span><input data-row-type="${type}" data-index="${index}" data-key="${service ? "service_type" : "description"}" value="${esc(service ? row.service_type : row.description)}"></label>
			<label><span>${service ? "Hours" : "Qty"}</span><input type="number" min="0.01" step="0.01" data-row-type="${type}" data-index="${index}" data-key="${service ? "hours" : "qty"}" value="${esc(service ? row.hours : row.qty)}"></label>
			<label><span>${service ? "Rate" : "Unit cost"}</span><input type="number" min="0" step="0.01" data-row-type="${type}" data-index="${index}" data-key="${service ? "rate" : "unit_cost"}" value="${esc(service ? row.rate : row.unit_cost)}"></label>
			<label><span>Coverage</span><select data-row-type="${type}" data-index="${index}" data-key="coverage_status">${["Pending Approval","Inside Warranty","Outside Warranty","Partially Covered"].map((value) => `<option ${value === row.coverage_status ? "selected" : ""}>${value}</option>`).join("")}</select></label>
			<button type="button" class="wp-remove" data-remove-row="${type}" data-index="${index}">Remove</button>
		</div>`;
	}

	function updateRow(event) {
		const collection = event.target.dataset.rowType === "part" ? parts : services;
		const numeric = ["qty","unit_cost","hours","rate","covered_amount"].includes(event.target.dataset.key);
		collection[Number(event.target.dataset.index)][event.target.dataset.key] = numeric ? Number(event.target.value) : event.target.value;
	}
	function removeRow(event) {
		(event.currentTarget.dataset.removeRow === "part" ? parts : services).splice(Number(event.currentTarget.dataset.index), 1);
		renderRows();
	}

	function renderCosts(costs) {
		const entries = [["Total repair",costs.total_repair_cost],["Warranty covered",costs.warranty_covered_amount],["Customer payable",costs.customer_payable_amount],["Provider claim",costs.provider_claim_amount]];
		$("#cost-summary").innerHTML = entries.map(([label, value]) => `<div class="wp-stat"><strong>${money(value, costs.currency)}</strong><span>${label}</span></div>`).join("");
	}
	function renderDocuments(documents) {
		$("#documents-list").innerHTML = documents.length ? documents.map((doc) => `<div class="wp-doc"><div><strong>${esc(doc.document_type)}</strong><br><small>${esc(doc.file_name)}</small></div>${doc.file_id ? `<a class="wp-secondary" href="/api/method/${API}download_claim_file?file_id=${encodeURIComponent(doc.file_id)}">Download</a>` : ""}</div>`).join("") : `<p>No documents uploaded.</p>`;
	}

	async function saveClaim(event) {
		event.preventDefault();
		if (!activeClaim) return;
		const form = event.currentTarget;
		const payload = {};
		["complaint","custom_failure_date","custom_current_odometer","custom_inspection_date","custom_technician_name","custom_diagnosis","custom_inspection_details","custom_root_cause","custom_provider_recommendation","custom_provider_reason","custom_provider_technical_notes","custom_other_charges","custom_other_covered_amount"].forEach((name) => { payload[name] = form.elements[name].value; });
		payload.parts = parts;
		payload.services = services;
		await renderClaim(await call("update_claim", {name: activeClaim.name, payload: JSON.stringify(payload)}, "POST"));
	}

	async function runAction(action) {
		await renderClaim(await call("apply_claim_action", {name: activeClaim.name, action}, "POST"));
	}

	async function uploadDocument() {
		const file = $("#document-file").files[0];
		if (!file || !activeClaim) return showAlert("Choose a file to upload.");
		const content = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(file); });
		await renderClaim(await call("upload_claim_file", {name: activeClaim.name, file_name: file.name, content, document_type: $("#document-type").value}, "POST"));
		$("#document-file").value = "";
	}

	$$(`[data-view]`).forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
	$$(`[data-view-link]`).forEach((button) => button.addEventListener("click", () => showView(button.dataset.viewLink)));
	$("#vin-search-form").addEventListener("submit", searchVin);
	$("#create-claim-form").addEventListener("submit", createClaim);
	$(`[data-close-dialog]`).addEventListener("click", () => $("#create-claim-dialog").close());
	$("#refresh-claims").addEventListener("click", loadClaims);
	$("#back-to-claims").addEventListener("click", () => showView("claims"));
	$("#claim-form").addEventListener("submit", saveClaim);
	$("#add-part").addEventListener("click", () => { parts.push({qty:1, unit_cost:0, coverage_status:"Pending Approval"}); renderRows(); });
	$("#add-service").addEventListener("click", () => { services.push({hours:1, rate:0, coverage_status:"Pending Approval"}); renderRows(); });
	$("#upload-document").addEventListener("click", uploadDocument);
	loadDashboard();
})();
