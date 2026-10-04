frappe.ui.form.on("Vehicle Warranty", {
	setup(frm) {
		frm.set_query("provider_contract", () => ({
			filters: { warranty_provider: frm.doc.warranty_provider, status: "Active" },
		}));
		frm.set_query("coverage_template", () => ({ filters: { active: 1 } }));
		frm.set_query("warranty_provider", () => ({ filters: { active: 1 } }));
		frm.set_query("renewal_of", () => ({ filters: { vin: frm.doc.vin, status: ["!=", "Active"] } }));
	},
	refresh(frm) {
		if (!frm.doc.warranty_provider) return;
		frm.add_custom_button(__("Service Branches"), () => {
			frappe.set_route("List", "Warranty Provider Branch", {
				warranty_provider: frm.doc.warranty_provider,
				active: 1,
			});
		}, __("View"));
		if (!frm.is_new()) {
			frm.add_custom_button(__("Warranty Claim"), () => {
				frappe.new_doc("Warranty Claim", { custom_vehicle_warranty: frm.doc.name });
			}, __("Create"));
			frm.add_custom_button(__("Renewal / Extension"), () => {
				frappe.new_doc("Vehicle Warranty", {
					renewal_of: frm.doc.name,
					is_extension: 1,
					vin: frm.doc.vin,
					vehicle_master: frm.doc.vehicle_master,
					customer: frm.doc.customer,
					warranty_provider: frm.doc.warranty_provider,
					coverage_template: frm.doc.coverage_template,
					company: frm.doc.company,
					status: "Draft",
				});
			}, __("Create"));
		}
	},
	vehicle_master(frm) {
		if (!frm.doc.vehicle_master) return;
		frappe.db.get_value("Vehicle Master", frm.doc.vehicle_master, ["vin", "customer", "sales_order", "delivery_note", "sales_invoice", "company"]).then(({ message }) => {
			if (!message) return;
			for (const field of ["vin", "customer", "sales_order", "delivery_note", "sales_invoice", "company"]) {
				if (message[field]) frm.set_value(field, message[field]);
			}
		});
	},
});
