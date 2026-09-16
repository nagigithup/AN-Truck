frappe.ui.form.on("Landed Cost Voucher", {
	setup(frm) {
		frm.set_query("custom_vehicle_import_file", () => ({
			filters: {
				company: frm.doc.company,
				status: ["!=", "Cancelled"],
			},
		}));
	},
});
