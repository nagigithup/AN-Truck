"""Derived vehicle costs from standard, audited serial revaluations."""
import frappe
from frappe.utils import flt

TARGET = "custom_portal_truck_cost_vehicle"
FIELD = "custom_portal_serial_cost_adjustment"


def valuation_basis(vehicle):
	"""None keeps every pre-feature vehicle on its existing cost calculation."""
	if not frappe.get_meta("Stock Reconciliation").has_field(TARGET) or not vehicle.name:
		return None
	docs = frappe.get_all("Stock Reconciliation",filters={TARGET:vehicle.name,"company":vehicle.company,
		"custom_portal_truck_cost_receipt_item":vehicle.purchase_receipt_item,"docstatus":["in",[1,2]]},
		fields=["docstatus","difference_amount"])
	if not docs: return None
	base = flt(frappe.db.get_value("Purchase Receipt Item",vehicle.purchase_receipt_item,"valuation_rate"))
	return base + sum(flt(d.difference_amount) for d in docs if d.docstatus==1)


def refresh_vehicle(doc, method=None):
	"""A trusted stock posting refreshes only its linked derived master summary."""
	if not doc.get(TARGET) or doc.docstatus not in (1,2): return
	if method=="on_change" and not frappe.flags.through_repost_item_valuation: return
	vehicle = frappe.get_doc("Vehicle Master",doc.get(TARGET),for_update=True)
	fields = ["purchase_valuation_rate","landed_cost_added","final_valuation_rate",FIELD]
	previous = [vehicle.get(f) for f in fields]
	vehicle.refresh_costs()
	if previous != [vehicle.get(f) for f in fields]:
		vehicle.save(ignore_permissions=True)
