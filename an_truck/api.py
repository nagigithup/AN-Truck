import frappe
from frappe import _


@frappe.whitelist()
def get_vehicle_import_summary(vehicle_import_file):
	if not frappe.has_permission("Vehicle Import File", "read", vehicle_import_file):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	vehicles = frappe.get_all(
		"Vehicle Master",
		filters={"vehicle_import_file": vehicle_import_file, "disabled": 0},
		fields=["vehicle_status", "final_vehicle_cost"],
	)
	status_counts = {}
	total_cost = 0
	for vehicle in vehicles:
		status_counts[vehicle.vehicle_status] = status_counts.get(vehicle.vehicle_status, 0) + 1
		total_cost += vehicle.final_vehicle_cost or 0

	import_file = frappe.get_doc("Vehicle Import File", vehicle_import_file)
	return {
		"expected": import_file.total_expected_vehicles,
		"received": import_file.total_received_vehicles,
		"in_stock": import_file.vehicles_in_stock,
		"remaining": import_file.vehicles_remaining,
		"status": import_file.status,
		"total_cost": total_cost,
		"currency": import_file.company_currency,
		"status_counts": status_counts,
	}
