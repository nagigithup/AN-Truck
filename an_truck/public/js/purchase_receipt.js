frappe.ui.form.on("Purchase Receipt", {
	setup(frm) {
		frm.set_query("custom_vehicle_import_file", () => ({
			filters: {
				company: frm.doc.company,
				supplier: frm.doc.supplier,
				status: ["!=", "Cancelled"],
			},
		}));
		frm.set_query("custom_vehicle_specification_template", "items", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return {
				query: "an_truck.an_truck.doctype.vehicle_specification_template.vehicle_specification_template.template_query",
				filters: { item_code: row.item_code },
			};
		});
	},
	refresh(frm) {
		if (frm.doc.custom_vehicle_import_file) {
			frm.add_custom_button(__("Vehicle Masters"), () => {
				frappe.set_route("List", "Vehicle Master", {
					vehicle_import_file: frm.doc.custom_vehicle_import_file,
					purchase_receipt: frm.doc.name,
				});
			}, __("View"));
		}
	},
});
