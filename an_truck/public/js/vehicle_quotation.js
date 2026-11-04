frappe.ui.form.on("Quotation", {
	setup(frm) {
		frm.set_query("custom_vehicle_specification_template", "items", (doc, cdt, cdn) => ({
			query: "an_truck.vehicle_quotation.template_query",
			filters: { item_code: locals[cdt][cdn].item_code },
		}));
		frm.set_query("custom_company_bank_account", () => ({
			filters: { company: frm.doc.company, is_company_account: 1, disabled: 0 },
		}));
	},
	refresh(frm) {
		if (!frm.is_new() && frm.doc.docstatus === 0 && frm.perm[0]?.write) {
			frm.add_custom_button(__("Refresh Quotation Specifications"), () => {
				if (frm.is_dirty()) return frappe.msgprint(__("Save your changes before refreshing specifications."));
				frappe.confirm(__("Refresh the draft quotation specifications and terms?"), async () => {
					await frappe.call({ method: "an_truck.vehicle_quotation.refresh_specifications", args: { name: frm.doc.name }, type: "POST" });
					frm.reload_doc();
				});
			});
		}
	},
});

frappe.ui.form.on("Quotation Item", {
	async custom_vehicle_master(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.custom_vehicle_master || row.custom_vehicle_specification_template) return;
		const selectedVehicle = row.custom_vehicle_master;
		const vehicle = await frappe.db.get_value("Vehicle Master", selectedVehicle, "specification_template");
		if (row.custom_vehicle_master === selectedVehicle && !row.custom_vehicle_specification_template && vehicle.message?.specification_template) {
			frappe.model.set_value(cdt, cdn, "custom_vehicle_specification_template", vehicle.message.specification_template);
		}
	},
});
