frappe.ui.form.on("Vehicle Master", {
	refresh(frm) {
		if (frm.is_new()) return;
		[
			["customer", "Customer", "Open Customer"],
			["quotation", "Quotation", "Open Quotation"],
			["sales_order", "Sales Order", "Open Sales Order"],
			["sales_invoice", "Sales Invoice", "Open Sales Invoice"],
			["delivery_note", "Delivery Note", "Open Delivery Note"],
		].forEach(([fieldname, doctype, label]) => {
			if (frm.doc[fieldname]) {
				frm.add_custom_button(
					__(label),
					() => frappe.set_route("Form", doctype, frm.doc[fieldname]),
					__("Sales & Warranty"),
				);
			}
		});
		frappe.call("an_truck.warranty.reporting.get_vehicle_warranty_summary", {vehicle_master: frm.doc.name}).then(({message}) => {
			if (!message) return;
			const warranty = message.warranty;
			const escape = frappe.utils.escape_html;
			frm.dashboard.add_section(`
				<div class="row">
					<div class="col-sm-3"><b>${__("Current Warranty Status")}</b><br>${escape(warranty?.status || __("No Warranty"))}</div>
					<div class="col-sm-3"><b>${__("Warranty Provider")}</b><br>${escape(warranty?.warranty_provider || "—")}</div>
					<div class="col-sm-3"><b>${__("Warranty Start")}</b><br>${frappe.datetime.str_to_user(warranty?.warranty_start_date || "")}</div>
					<div class="col-sm-3"><b>${__("Warranty Expiry")}</b><br>${frappe.datetime.str_to_user(warranty?.warranty_expiry_date || "")}</div>
				</div><div class="row mt-3">
					<div class="col-sm-3"><b>${__("Coverage Template")}</b><br>${escape(warranty?.coverage_template || "—")}</div>
					<div class="col-sm-3"><b>${__("Number of Claims")}</b><br>${message.number_of_claims}</div>
					<div class="col-sm-3"><b>${__("Total Warranty Cost")}</b><br>${format_currency(message.total_warranty_cost)}</div>
					<div class="col-sm-3"><b>${__("Open Claims")}</b><br>${message.open_claims}</div>
				</div>`, __("Warranty Summary"), "warranty-summary");
			if (warranty) {
				frm.add_custom_button(__("Open Vehicle Warranty"), () => frappe.set_route("Form", "Vehicle Warranty", warranty.name), __("Warranty"));
				frm.add_custom_button(__("View Warranty Claims"), () => { frappe.route_options = {custom_vehicle_master: frm.doc.name}; frappe.set_route("List", "Warranty Claim"); }, __("Warranty"));
				frm.add_custom_button(__("Create Warranty Claim"), () => frappe.new_doc("Warranty Claim", {custom_vehicle_warranty: warranty.name}), __("Warranty"));
				frm.add_custom_button(__("Warranty History"), () => { frappe.route_options = {vin: frm.doc.vin}; frappe.set_route("query-report", "Warranty Claim History by VIN"); }, __("Warranty"));
			}
		});
	},
});
