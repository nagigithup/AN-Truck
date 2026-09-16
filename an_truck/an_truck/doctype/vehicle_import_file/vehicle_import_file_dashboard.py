from frappe import _

from an_truck.services import CUSTOM_FIELD


def get_data():
	return {
		"fieldname": CUSTOM_FIELD,
		"non_standard_fieldnames": {
			"Vehicle Master": "vehicle_import_file",
			"Vehicle": CUSTOM_FIELD,
		},
		"transactions": [
			{
				"label": _("Purchasing"),
				"items": [
					"Purchase Order",
					"Purchase Receipt",
					"Purchase Invoice",
					"Payment Entry",
					"Landed Cost Voucher",
				],
			},
			{
				"label": _("Vehicle"),
				"items": [
					"Vehicle Master",
					"Vehicle",
				],
			},
			{
				"label": _("Sales"),
				"items": [
					"Quotation",
					"Sales Order",
					"Delivery Note",
					"Sales Invoice",
					"Payment Entry",
				],
			},
		],
	}
