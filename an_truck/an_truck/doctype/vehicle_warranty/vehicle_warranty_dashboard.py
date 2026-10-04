from frappe import _


def get_data():
	return {
		"fieldname": "custom_vehicle_warranty",
		"transactions": [{"label": _("Claims"), "items": ["Warranty Claim"]}],
	}

