frappe.ui.form.on("Vehicle Warranty", {
	setup(frm) {
		frm.set_query("vin", () => ({ filters: { disabled: 0 } }));
		frm.set_query("coverage_template", () => ({ filters: { active: 1 } }));
		frm.set_query("renewal_of", () => ({ filters: { vin: frm.doc.vin, status: ["!=", "Active"] } }));
	},
	refresh(frm) {
		render_summary(frm);
		refresh_configuration(frm);
		if (frm.doc.warranty_provider) {
			frm.add_custom_button(__("Service Branches"), () => {
				frappe.set_route("List", "Warranty Provider Branch", {
					warranty_provider: frm.doc.warranty_provider, active: 1,
				});
			}, __("View"));
		}
		if (!frm.is_new()) {
			frm.add_custom_button(__("Warranty Claim"), () => {
				frappe.new_doc("Warranty Claim", { custom_vehicle_warranty: frm.doc.name });
			}, __("Create"));
			frm.add_custom_button(__("Renewal / Extension"), () => {
				frappe.new_doc("Vehicle Warranty", {
					renewal_of: frm.doc.name, is_extension: 1, vin: frm.doc.vin,
					coverage_template: frm.doc.coverage_template,
				});
			}, __("Create"));
		}
	},
	vin: load_vehicle,
	coverage_template: refresh_configuration,
	warranty_start_date: refresh_configuration,
	warranty_provider: refresh_configuration,
});

async function load_vehicle(frm) {
	if (!frm.doc.vin) return;
	const { message } = await frappe.call({
		method: "an_truck.warranty.workflow.get_vehicle_warranty_context",
		args: { vin: frm.doc.vin },
	});
	if (!message) return;
	await frm.set_value({
		vehicle_master: message.vehicle_master, customer: message.customer?.name,
		company: message.company, sales_order: message.sales_order,
		delivery_note: message.delivery_note, sales_invoice: message.sales_invoice,
	});
	if (!frm.doc.warranty_start_date && message.start_date) {
		await frm.set_value("warranty_start_date", message.start_date);
	}
	render_summary(frm, message);
}

async function refresh_configuration(frm) {
	if (!(frm.doc.vehicle_master && frm.doc.coverage_template && frm.doc.warranty_start_date)) return;
	const { message } = await frappe.call({
		method: "an_truck.warranty.workflow.get_warranty_configuration",
		args: { vehicle_master: frm.doc.vehicle_master, coverage_template: frm.doc.coverage_template,
			start_date: frm.doc.warranty_start_date, provider: frm.doc.warranty_provider || undefined },
	});
	if (!message) return;
	frm.toggle_display("warranty_provider", message.providers.length > 1);
	frm.toggle_display("provider_contract", message.contracts.length > 1);
	if (!frm.doc.warranty_provider && message.provider) await frm.set_value("warranty_provider", message.provider);
	const validContracts = message.contracts.map((row) => row.name);
	if (frm.doc.provider_contract && !validContracts.includes(frm.doc.provider_contract)) await frm.set_value("provider_contract", "");
	if (!frm.doc.provider_contract && message.contract) await frm.set_value("provider_contract", message.contract);
	await frm.set_value("warranty_expiry_date", message.expiry_date);
	const template = await frappe.db.get_value("Warranty Coverage Template", frm.doc.coverage_template, ["duration", "duration_unit"]);
	if (template.message) await frm.set_value(template.message);
}

function render_summary(frm, context) {
	const escape = frappe.utils.escape_html;
	const vehicleLabel = context?.vehicle?.label || frm.doc.vehicle_model || frm.doc.item_code || "—";
	const customerLabel = context?.customer?.label || frm.doc.customer || "—";
	frm.fields_dict.vehicle_summary?.$wrapper.html(`<div class="form-message blue"><b>${__("Vehicle Summary")}</b><br>${escape(vehicleLabel)}</div>`);
	frm.fields_dict.customer_summary?.$wrapper.html(`<div class="form-message blue"><b>${__("Customer Summary")}</b><br>${escape(customerLabel)}</div>`);
}
