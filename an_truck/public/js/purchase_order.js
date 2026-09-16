frappe.ui.form.on("Purchase Order", {
	setup(frm) {
		set_import_file_query(frm);
	},
	custom_vehicle_import_file(frm) {
		apply_import_file_defaults(frm);
	},
});

function set_import_file_query(frm) {
	frm.set_query("custom_vehicle_import_file", () => ({
		filters: {
			company: frm.doc.company,
			supplier: frm.doc.supplier,
			status: ["!=", "Cancelled"],
		},
	}));
}

function apply_import_file_defaults(frm) {
	if (!frm.doc.custom_vehicle_import_file) return;
	frappe.db.get_value("Vehicle Import File", frm.doc.custom_vehicle_import_file, ["company", "supplier", "supplier_currency"]).then((r) => {
		const values = r.message || {};
		["company", "supplier"].forEach((fieldname) => {
			if (values[fieldname]) frm.set_value(fieldname, values[fieldname]);
		});
		if (values.supplier_currency) frm.set_value("currency", values.supplier_currency);
	});
}
