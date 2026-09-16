frappe.ui.form.on("Purchase Receipt", {
	setup(frm) {
		frm.set_query("custom_vehicle_import_file", () => ({
			filters: {
				company: frm.doc.company,
				supplier: frm.doc.supplier,
				status: ["!=", "Cancelled"],
			},
		}));
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
