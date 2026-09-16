frappe.pages["an-truck-portal"].on_page_load = function (wrapper) {
	wrapper.an_truck_portal = new ANTruckPortal(wrapper);
};

frappe.pages["an-truck-portal"].on_page_show = function (wrapper) {
	wrapper.an_truck_portal.refresh();
};

class ANTruckPortal {
	constructor(wrapper) {
		this.page = frappe.ui.make_app_page({parent: wrapper, title: __("AN Truck"), single_column: true});
		this.page.main.addClass("an-truck-home");
		this.styles = frappe.require("/assets/an_truck/css/portal.css");
		this.page.set_secondary_action(__("Refresh"), () => this.refresh(), "refresh-cw");
	}

	async refresh() {
		if (this.loading) return;
		this.loading = true;
		await this.styles;
		this.page.main.attr("aria-busy", "true");
		try {
			const {message: data} = await frappe.call("an_truck.portal.get_portal_data");
			this.render(data);
		} catch (error) {
			this.page.main.html(`<div class="text-muted p-4" role="alert">${__("Unable to load the overview. Please try again.")}</div>`);
		} finally {
			this.loading = false;
			this.page.main.attr("aria-busy", "false");
		}
	}

	render(data) {
		const escape = frappe.utils.escape_html;
		this.page.main.html(`
			<header class="an-home-heading">
				<h2>${__("Overview")}</h2>
				<div class="text-muted">${escape(data.company || "")} <span>${escape(data.date || "")}</span></div>
			</header>
			<div class="an-home-metrics">
				${(data.kpis || []).map((card, index) => `
					<button type="button" class="an-home-metric" data-index="${index}">
						<span class="an-home-metric-label">${frappe.utils.icon(card.icon, "md")} ${escape(card.label)}</span>
						<strong>${escape(String(card.value ?? 0))}</strong>
					</button>`).join("")}
			</div>
		`);
		this.page.main.find("[data-index]").on("click", function () {
			const card = data.kpis[Number(this.dataset.index)];
			frappe.route_options = card.filters || {};
			frappe.set_route("List", card.doctype);
		});
	}
}
