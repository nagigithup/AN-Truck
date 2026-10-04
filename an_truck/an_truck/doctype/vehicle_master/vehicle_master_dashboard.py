from frappe import _


def get_data():
	return {
		"fieldname": "vehicle_master",
		"non_standard_fieldnames": {"Warranty Claim": "custom_vehicle_master"},
		"transactions": [{"label": _("Warranty"), "items": ["Vehicle Warranty", "Warranty Claim"]}],
	}
