frappe.ui.form.on("Purchase Invoice", {
	setup(frm) {
		frm.set_query("custom_vehicle_import_file", () => ({
			filters: {
				company: frm.doc.company,
				supplier: frm.doc.supplier,
				status: ["!=", "Cancelled"],
			},
		}));
	},
});
