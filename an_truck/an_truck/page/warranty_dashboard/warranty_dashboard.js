frappe.pages["warranty-dashboard"].on_page_load = function (wrapper) {
	wrapper.warranty_dashboard = new WarrantyDashboard(wrapper);
};

frappe.pages["warranty-dashboard"].on_page_show = function (wrapper) {
	wrapper.warranty_dashboard.refresh();
};

class WarrantyDashboard {
	constructor(wrapper) {
		this.page = frappe.ui.make_app_page({parent: wrapper, title: __("Warranty Dashboard"), single_column: true});
		this.page.main.addClass("warranty-dashboard-page");
		this.styles = frappe.require("/assets/an_truck/css/warranty_dashboard.css");
		this.company = this.page.add_field({
			label: __("Company"), fieldtype: "Link", options: "Company", fieldname: "company",
			default: frappe.defaults.get_user_default("Company"), change: () => this.refresh(),
		});
		this.page.set_secondary_action(__("Refresh"), () => this.refresh(), "refresh-cw");
	}

	async refresh() {
		if (this.loading) return;
		this.loading = true;
		await this.styles;
		try {
			const {message} = await frappe.call("an_truck.warranty.reporting.get_warranty_dashboard", {company: this.company.get_value()});
			this.render(message);
		} finally {
			this.loading = false;
		}
	}

	render(data) {
		this.page.main.html(`
			<section class="warranty-lookup-card">
				<div><h3>${__("Warranty Lookup by VIN")}</h3><p class="text-muted">${__("Open the complete after-sales warranty and claim history for a truck.")}</p></div>
				<div class="warranty-vin-search"><input class="form-control" data-vin maxlength="64" placeholder="${__("Enter complete VIN")}"><button class="btn btn-primary" data-vin-search>${__("Lookup")}</button></div>
				<div data-vin-result></div>
			</section>
			<h3>${__("Warranty Operations")}</h3><div class="warranty-kpi-grid">${data.kpis.map((card, index) => this.card(card, index)).join("")}</div>
			<h3>${__("Financial KPIs")}</h3><div class="warranty-kpi-grid financial">${data.financial_kpis.map(card => this.financialCard(card)).join("")}</div>
			<h3>${__("Management Analytics")}</h3><div class="warranty-chart-grid">${data.charts.map((chart, index) => `<article class="warranty-chart-card"><h4>${frappe.utils.escape_html(chart.title)}</h4><div data-chart="${index}"></div></article>`).join("")}</div>
		`);
		this.page.main.find("[data-kpi]").on("click", (event) => {
			const card = data.kpis[Number(event.currentTarget.dataset.kpi)];
			frappe.route_options = card.filters || {};
			frappe.set_route("List", card.doctype);
		});
		this.page.main.find("[data-vin-search]").on("click", () => this.lookupVin());
		this.page.main.find("[data-vin]").on("keydown", (event) => { if (event.key === "Enter") this.lookupVin(); });
		data.charts.forEach((chart, index) => this.drawChart(index, chart));
	}

	card(card, index) {
		return `<button class="warranty-kpi-card" data-kpi="${index}"><span>${frappe.utils.escape_html(card.label)}</span><strong>${frappe.format(card.value, {fieldtype:"Int"})}</strong></button>`;
	}

	financialCard(card) {
		return `<div class="warranty-kpi-card"><span>${frappe.utils.escape_html(card.label)}</span><strong>${format_currency(card.value, card.currency)}</strong></div>`;
	}

	drawChart(index, chart) {
		const target = this.page.main.find(`[data-chart="${index}"]`)[0];
		if (!target || !chart.labels.length) {
			target.innerHTML = `<p class="text-muted">${__("No data")}</p>`;
			return;
		}
		new frappe.Chart(target, {data: {labels: chart.labels, datasets: chart.datasets}, type: chart.type, height: 260, colors: ["#176b4d", "#d08c35", "#5c7cba"]});
	}

	async lookupVin() {
		const vin = this.page.main.find("[data-vin]").val().trim();
		if (!vin) return;
		const {message} = await frappe.call("an_truck.warranty.reporting.get_vehicle_warranty_summary", {vin});
		const result = this.page.main.find("[data-vin-result]");
		const warranty = message.warranty;
		result.html(`<div class="vin-result"><b>${frappe.utils.escape_html(message.vehicle.vin)}</b> · ${frappe.utils.escape_html(message.vehicle.item_name || "")}
			<span>${warranty ? frappe.utils.escape_html(warranty.status) : __("No Warranty")}</span>
			<div class="vin-actions">
				<a data-route="vehicle">${__("Vehicle Master")}</a>
				${warranty ? `<a data-route="warranty">${__("Vehicle Warranty")}</a><a data-route="claims">${__("Warranty Claims")}</a><a data-route="history">${__("Cost / History")}</a>` : ""}
			</div></div>`);
		result.find('[data-route="vehicle"]').on("click", () => frappe.set_route("Form", "Vehicle Master", message.vehicle.name));
		result.find('[data-route="warranty"]').on("click", () => frappe.set_route("Form", "Vehicle Warranty", warranty.name));
		result.find('[data-route="claims"]').on("click", () => { frappe.route_options = {serial_no: message.vehicle.vin}; frappe.set_route("List", "Warranty Claim"); });
		result.find('[data-route="history"]').on("click", () => { frappe.route_options = {vin: message.vehicle.vin}; frappe.set_route("query-report", "Warranty Claim History by VIN"); });
	}
}
