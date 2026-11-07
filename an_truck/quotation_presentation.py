"""Read-only layout adapter for the original ANYUAN quotation sheets.

Consumes the existing revision/snapshot payload; never reads a newer template
for a submitted quotation, calculates tax, or supplies model specifications.
"""
import math
import re
import textwrap

from frappe.utils import cstr, flt, strip_html


GROUPS = (
	("المحرك", "ENGINE", ("engine_model", "horsepower_hp", "engine_displacement_l", "maximum_torque_nm", "emission_standard", "engine_type", "number_of_cylinders", "fuel_type", "fuel_consumption", "fuel_consumption_unit_description")),
	("ناقل الحركة والكلتش", "TRANSMISSION & CLUTCH", ("transmission_brand", "transmission_model", "transmission", "forward_gears", "reverse_gears", "gear_ratio_details", "clutch_brand", "clutch_type", "clutch_specification")),
	("المحاور والفرامل والتعليق", "AXLES, BRAKES & SUSPENSION", ("number_of_axles", "front_axle_brand", "front_axle_type", "front_axle_capacity_ton", "rear_axle_brand", "rear_axle_type", "rear_axle_capacity_ton", "rear_axle_ratio", "brake_system_type", "abs", "brake_system_brand", "brake_system_description", "front_suspension_type", "rear_suspension_type", "suspension_description")),
	("المقصورة والتجهيزات", "CABIN & EQUIPMENT", ("cabin_type", "number_of_seats", "sleeper_bed", "air_conditioning", "safety_features", "cabin_features_equipment")),
	("الهيكل والإطارات وخزان الوقود", "CHASSIS, TIRES & FUEL TANK", ("front_tyre_size", "rear_tyre_size", "number_of_tyres", "tyre_specification_notes", "fuel_tank_material", "fuel_tank_capacity_l", "number_of_fuel_tanks", "fifth_wheel_size", "fifth_wheel_brand", "fifth_wheel_type")),
	("الأبعاد والأوزان", "DIMENSIONS & WEIGHTS", ("overall_chassis_length_mm", "vehicle_width_mm", "cab_height_mm", "wheelbase_mm", "curb_weight_kg", "gross_vehicle_weight_kg", "gross_combination_weight_kg", "payload_capacity", "payload_capacity_unit")),
)
SHORT_LABELS = {
	"engine_model": ("الطراز", "Model"), "horsepower_hp": ("القوة", "Horsepower"),
	"engine_displacement_l": ("السعة", "Displacement"), "maximum_torque_nm": ("العزم", "Max Torque"),
	"emission_standard": ("الانبعاثات", "Emission"), "transmission_model": ("طراز القير", "Gearbox"),
	"transmission": ("نظام التحكم", "Control"), "clutch_specification": ("الكلتش", "Clutch"),
	"front_tyre_size": ("الإطارات الأمامية", "Front Tires"), "rear_tyre_size": ("الإطارات الخلفية", "Rear Tires"),
	"fuel_tank_capacity_l": ("خزان الوقود", "Fuel Tank"), "gross_vehicle_weight_kg": ("الوزن الإجمالي", "GVW"),
}
UNITS = {"horsepower_hp": "HP", "maximum_torque_nm": "N.m", "engine_displacement_l": "L", "fuel_tank_capacity_l": "L"}
IDENTITY = {"brand", "model", "model_year", "vehicle_type"}


def text(value):
	return strip_html(cstr(value).replace("</p>", "\n").replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")).strip()


def _value(field):
	value = field.get("value")
	if field.get("fieldtype") == "Check":
		return "نعم / Yes" if value else "لا / No"
	if field.get("fieldtype") in {"Float", "Int", "Currency", "Percent"}:
		value = f"{flt(value):g}"
	unit = UNITS.get(field.get("fieldname"), "")
	if unit and cstr(value).rstrip().endswith(unit):
		unit = ""
	return f"{value} {unit}".strip()


def _cards(rows, ar, en):
	"""Bound every card's line count; split long values without dropping text."""
	cards, current, used = [], [], 0
	for row in rows:
		parts = textwrap.wrap(cstr(row["value"]), width=100, replace_whitespace=False, drop_whitespace=False) or [""]
		for index, value in enumerate(parts):
			entry = {**row, "value": value, "continuation": bool(index)}
			weight = max(math.ceil(len(value) / 40), math.ceil((len(row["ar"]) + len(row["en"])) / 34), 2)
			if current and used + weight > 14:
				cards.append({"ar": ar, "en": en, "rows": current})
				current, used = [], 0
			current.append(entry)
			used += weight
	if current:
		cards.append({"ar": ar, "en": en, "rows": current})
	return cards


def _commercial_preview(value):
	lines = []
	for paragraph in value.splitlines():
		lines.extend(textwrap.wrap(paragraph, width=50, replace_whitespace=False, drop_whitespace=False) or [""])
	return '\n'.join(lines[:8]), len(lines) > 8


def model_sheet(model):
	fields, extra, categorized = {}, [], {}
	for section in model.get("sections", []):
		for field in section.get("fields", []):
			if field["fieldtype"] == "Table":
				for row in field.get("value", []):
					entry = {"ar": row.get("specification_name") or "", "en": "",
						"value": " ".join(cstr(row.get(key) or "") for key in ("value", "uom", "notes")).strip()}
					category = row.get("specification_category") or ""
					match = next((en for ar, en, _names in GROUPS if category in (ar, en)), None)
					if match:
						categorized.setdefault(match, []).append(entry)
					else:
						extra.append(entry)
			elif field["fieldtype"] != "Attach" and field.get("value") not in (None, ""):
				fields[field["fieldname"]] = field
	cards, handled = [], set(IDENTITY)
	for ar, en, names in GROUPS:
		rows = []
		for name in names:
			if field := fields.get(name):
				label_ar, label_en = SHORT_LABELS.get(name, (field.get("label_ar") or field.get("label") or name, field.get("label_en") or field.get("label") or name))
				rows.append({"ar": label_ar, "en": label_en, "value": _value(field)})
			handled.add(name)
		cards.extend(_cards(rows + categorized.get(en, []), ar, en))
	for name, field in fields.items():
		if name not in handled:
			extra.append({"ar": field.get("label_ar") or field.get("label") or name,
				"en": field.get("label_en") or field.get("label") or name, "value": _value(field)})
	cards.extend(_cards(extra, "مواصفات إضافية", "ADDITIONAL SPECIFICATIONS"))
	images = model.get("images") or {}
	kc = "KC" in cstr(model.get("model_name_en")).upper().split() and "6X4" in cstr(model.get("model_name_en")).upper().replace("×", "X")
	photos = []
	for key in (("technical_photo",) if kc else ("technical_photo", "cabin_photo")):
		if images.get(key) and images[key] not in photos:
			photos.append(images[key])
	if not photos and images.get("main_vehicle_photo"):
		photos.append(images["main_vehicle_photo"])
	if kc:
		rank = {name: index for index, name in enumerate(("ENGINE", "TRANSMISSION & CLUTCH", "AXLES, BRAKES & SUSPENSION", "DIMENSIONS & WEIGHTS", "CHASSIS, TIRES & FUEL TANK"))}
		cards.sort(key=lambda card: rank.get(card["en"], 99))
	badges = []
	for name, ar, en in (("horsepower_hp", "القوة", "Horsepower"), ("maximum_torque_nm", "العزم", "Max Torque"),
		("transmission", "ناقل الحركة", "Transmission"), ("fuel_tank_capacity_l", "خزان الوقود", "Fuel Tank"), ("gross_vehicle_weight_kg", "الوزن الإجمالي", "GVW")):
		value = _value(fields[name]) if name in fields else ""
		if not value:
			value = next((row["value"] for rows in categorized.values() for row in rows if en.casefold() in row["ar"].casefold()), "")
		if name == "transmission" and not value:
			rows = categorized.get("TRANSMISSION & CLUTCH", [])
			control = next((row["value"] for row in rows if "control" in row["ar"].lower()), "")
			gears = next((row["value"] for row in rows if "gears" in row["ar"].lower()), "")
			match = re.search(r'(\d+)\s*Forward\s*\+\s*(\d+)\s*Reverse', gears, re.I)
			value = f'{control} {match[1]}+{match[2]}' if match else control
		if name == "gross_vehicle_weight_kg" and value and not value.rstrip().endswith("kg"):
			value += " kg"
		if name != "transmission" and (match := re.search(r'([≤<≥>]?[\s\d,.]+)\s*(HP|N\.m|L|kg)', value, re.I)):
			value = f'{match[1].strip()} {match[2]}'
		badges.append({"ar": ar, "en": en, "value": value})
	return {"model": model, "fields": fields, "photos": photos, "badges": badges,
		"kc": kc, "card_pages": [cards[i:i+6] for i in range(0, len(cards), 6)],
		"image_pages": [(model.get("additional_images") or [])[i:i+2] for i in range(0, len(model.get("additional_images") or []), 2)]}


def layout(doc, data):
	"""One original commercial sheet per item; document totals appear only once."""
	sheets, appendices = [], []
	for index, row in enumerate(doc.items):
		model = data["lines"][index]
		warranty = text(model.get("warranty_terms") or row.get("custom_vehicle_warranty_terms"))
		delivery = text(model.get("delivery_terms") or row.get("custom_vehicle_delivery_terms"))
		arabic, english = [], []
		for line in warranty.splitlines():
			(arabic if any('\u0600' <= char <= '\u06ff' for char in line) else english).append(line)
		ar_preview, ar_overflow = _commercial_preview('\n'.join(arabic))
		en_preview, en_overflow = _commercial_preview('\n'.join(english))
		sheets.append({"row": row, "spec": model, "sheet": model_sheet(model),
			"warranty": warranty, "warranty_ar": ar_preview, "warranty_en": en_preview,
			"delivery": ' '.join(delivery.split())[:90], "description": text(row.description)[:70],
			"show_description": text(row.description) not in (row.item_name, row.item_code), "last": index == len(doc.items)-1})
		if ar_overflow or en_overflow:
			appendices.append({"title":f"{row.item_name} — Warranty / الضمان", "value":warranty})
		for label, value, limit in (("Delivery / التسليم", delivery, 90), ("Description / الوصف", text(row.description), 70)):
			if len(value) > limit:
				appendices.append({"title": f"{row.item_name} — {label}", "value": value})
	for label, value in (("الشروط التجارية / COMMERCIAL TERMS", text(doc.terms)), ("ملاحظات / NOTES", text(doc.get("custom_vehicle_quotation_notes")))):
		if value:
			appendices.append({"title": label, "value": value})
	for payment in doc.get("payment_schedule") or []:
		appendices.append({"title": "شروط الدفع / PAYMENT TERMS", "value": f"{payment.payment_term or ''} · {payment.due_date or ''} · {payment.payment_amount} {doc.currency}"})
	if doc.get("address_display") or data.get("customer", {}).get("tax_id"):
		appendices.append({"title": "بيانات العميل / CUSTOMER DETAILS", "value": '\n'.join(filter(None, [text(doc.get("address_display")), data.get("customer", {}).get("tax_id")]))})
	company_address = ' '.join(text(data.get('company', {}).get('address')).split())
	if len(company_address) > 220:
		appendices.append({"title":"عنوان الشركة / COMPANY ADDRESS", "value":company_address})
	blocks = []
	for part in appendices:
		lines = []
		for paragraph in part["value"].splitlines():
			lines.extend(textwrap.wrap(paragraph, width=95, replace_whitespace=False, drop_whitespace=False) or [""])
		for index in range(0, len(lines), 30):
			blocks.append({"title": part["title"], "value": '\n'.join(lines[index:index+30])})
	return {"commercial_sheets": sheets, "technical_sheets": [model_sheet(model) for model in data["models"]],
		"footer_address": company_address[:220],
		"tax_pages": [data.get("tax_rows", [])[i:i+12] for i in range(0, len(data.get("tax_rows", [])), 12)] or [[]],
		"appendices": blocks}
