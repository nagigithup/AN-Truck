import frappe


def execute():
	for name in frappe.get_all(
		"Vehicle Master",
		filters={"purchase_receipt_item": ["is", "set"]},
		pluck="name",
	):
		vehicle = frappe.get_doc("Vehicle Master", name)
		vehicle.refresh_costs()
		frappe.db.set_value(
			"Vehicle Master",
			name,
			{
				"purchase_valuation_rate": vehicle.purchase_valuation_rate,
				"landed_cost_added": vehicle.landed_cost_added,
				"final_valuation_rate": vehicle.final_valuation_rate,
			},
			update_modified=False,
		)
