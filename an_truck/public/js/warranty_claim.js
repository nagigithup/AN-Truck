frappe.ui.form.on("Warranty Claim", {
	setup(frm) {
		frm.set_query("custom_warranty_provider_branch", () => ({
			filters: { warranty_provider: frm.doc.custom_warranty_provider, active: 1 },
		}));
		frm.set_query("custom_vehicle_warranty", () => ({ filters: { status: ["!=", "Cancelled"] } }));
	},
	custom_vehicle_warranty(frm) {
		if (!frm.doc.custom_vehicle_warranty) return;
		frappe.db.get_value("Vehicle Warranty", frm.doc.custom_vehicle_warranty, ["vin", "vehicle_master", "customer", "warranty_provider", "company", "currency"]).then(({ message }) => {
			if (!message) return;
			frm.set_value({
				serial_no: message.vin,
				custom_vehicle_master: message.vehicle_master,
				customer: message.customer,
				custom_warranty_provider: message.warranty_provider,
				company: message.company,
				custom_currency: message.currency,
			});
		});
	},
	custom_other_charges: calculate_claim_totals,
	custom_other_covered_amount: calculate_claim_totals,
});

frappe.ui.form.on("Warranty Claim Part", {
	qty: calculate_claim_totals,
	unit_cost: calculate_claim_totals,
	coverage_status: calculate_claim_totals,
	covered_amount: calculate_claim_totals,
	custom_parts_remove: calculate_claim_totals,
});

frappe.ui.form.on("Warranty Claim Service", {
	hours: calculate_claim_totals,
	rate: calculate_claim_totals,
	coverage_status: calculate_claim_totals,
	covered_amount: calculate_claim_totals,
	custom_services_remove: calculate_claim_totals,
});

frappe.ui.form.on("Warranty Claim Document", {
	invoice_amount: calculate_document_total,
	vat_amount: calculate_document_total,
});

function split_coverage(row, total) {
	if (row.coverage_status === "Inside Warranty") return [total, 0];
	if (row.coverage_status === "Outside Warranty") return [0, total];
	if (row.coverage_status === "Partially Covered") {
		const covered = Math.min(Math.max(flt(row.covered_amount), 0), total);
		return [covered, total - covered];
	}
	return [0, 0];
}

function calculate_claim_totals(frm) {
	let partsTotal = 0, partsCovered = 0, partsCustomer = 0;
	let laborTotal = 0, laborCovered = 0, laborCustomer = 0;
	for (const row of frm.doc.custom_parts || []) {
		const total = flt(row.qty) * flt(row.unit_cost);
		const [covered, customer] = split_coverage(row, total);
		frappe.model.set_value(row.doctype, row.name, "total_cost", total);
		frappe.model.set_value(row.doctype, row.name, "customer_payable_amount", customer);
		if (row.coverage_status !== "Partially Covered") frappe.model.set_value(row.doctype, row.name, "covered_amount", covered);
		partsTotal += total; partsCovered += covered; partsCustomer += customer;
	}
	for (const row of frm.doc.custom_services || []) {
		const total = flt(row.hours) * flt(row.rate);
		const [covered, customer] = split_coverage(row, total);
		frappe.model.set_value(row.doctype, row.name, "amount", total);
		frappe.model.set_value(row.doctype, row.name, "customer_payable_amount", customer);
		if (row.coverage_status !== "Partially Covered") frappe.model.set_value(row.doctype, row.name, "covered_amount", covered);
		laborTotal += total; laborCovered += covered; laborCustomer += customer;
	}
	const other = flt(frm.doc.custom_other_charges);
	const otherCovered = Math.min(Math.max(flt(frm.doc.custom_other_covered_amount), 0), other);
	frm.set_value({
		custom_parts_inside_warranty: partsCovered,
		custom_parts_outside_warranty: partsCustomer,
		custom_labor_inside_warranty: laborCovered,
		custom_labor_outside_warranty: laborCustomer,
		custom_total_repair_cost: partsTotal + laborTotal + other,
		custom_warranty_covered_amount: partsCovered + laborCovered + otherCovered,
		custom_customer_payable_amount: partsCustomer + laborCustomer + other - otherCovered,
		custom_provider_claim_amount: partsCovered + laborCovered + otherCovered,
	});
}

function calculate_document_total(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "total_including_vat", flt(row.invoice_amount) + flt(row.vat_amount));
}

