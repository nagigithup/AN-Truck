"""Dev-only reference preview: no templates, quotations or business data saved.

Pass the user's two original HTML files. All demo specifications/images come
from those files; company facts and amounts remain those of the source quotation.
The reference fixture is an in-memory submitted snapshot, NOT a real submission.
"""
import copy
import json
import re
from pathlib import Path

import frappe


def generate(reference_files, output="/tmp/anyuan-quotation-review", source="SAL-QTN-2026-00007"):
	from bs4 import BeautifulSoup
	from an_truck import vehicle_quotation as domain
	frappe.only_for("System Manager")
	root = Path(output)
	root.mkdir(parents=True, exist_ok=True)
	original = frappe.get_doc("Quotation", source)
	original.check_permission("print")
	before = original.as_json()
	context = domain._commercial_context(original)
	for path in reference_files:
		html = Path(path).read_text()
		ref = BeautifulSoup(html, "html.parser")
		model = ref.select_one('.hero .model').get_text(strip=True)
		key = "dongfeng" if "DONGFENG" in model else "h7-pro"
		main = ref.select_one('.hero .photo img')
		main = main.get('src') if main else re.search(r"url\(['\"]?(data:image/[^)'\"]+)", html).group(1)
		cab = [img['src'] for img in ref.select('.p1 .cab img')]
		technical = [img['src'] for img in ref.select('.p2 .cabshow img')]
		rows = []
		for box in ref.select('.p2 .specbox'):
			category = box.select_one('.enh2').get_text(' ', strip=True)
			for row in box.select('tr'):
				cells = row.find_all('td')
				rows.append({'specification_category':category, 'specification_name':cells[0].get_text(' ',strip=True), 'value':cells[1].get_text(' ',strip=True)})
		warranty = '\n'.join(row.get_text(' ',strip=True) for col in ref.select('.warrcol') for row in col.find_all('div',recursive=False))
		data = {'schema_version':1, 'template':'REFERENCE-ONLY-'+key, 'revision':1,
			'model_name_en':model,'model_name_ar':ref.select_one('.arname').get_text(' ',strip=True),
			'configuration':next(option.get_text(' ',strip=True) for option in ref.select('#cab_type option') if option.get('value') != ''),
			'highlights':ref.select_one('.hero .sub').get_text(' ',strip=True),
			'images':{'main_vehicle_photo':main, 'technical_photo':technical[0], 'cabin_photo':cab[-1]},
			'sections':[{'label':'Reference specifications','fields':[{'fieldname':'technical_specifications','fieldtype':'Table','value':rows}]}],
			'warranty_terms':warranty, 'delivery_terms':ref.select_one('.termrow .fixed').get_text(' ',strip=True)}
		doc = frappe.get_doc(copy.deepcopy(original.as_dict()))
		doc.name = 'DESIGN-PREVIEW-'+key.upper()
		doc.docstatus = 1
		doc.custom_vehicle_quotation_context = json.dumps(context)
		doc.items = [doc.items[0]]
		doc.items[0].set(domain.SNAPSHOT, json.dumps(data))
		doc.terms = ''
		doc.custom_vehicle_quotation_notes = ''
		doc.payment_schedule = []
		# Preview the exact submitted-snapshot rendering path. Never insert/save/submit.
		(root / f'{key}.html').write_text(frappe.get_print('Quotation',doc.name,domain.PRINT_FORMAT,doc=doc,no_letterhead=1))
		(root / f'{key}.pdf').write_bytes(frappe.get_print('Quotation',doc.name,domain.PRINT_FORMAT,doc=doc,no_letterhead=1,as_pdf=True,pdf_generator='chrome'))
		(root / f'{key}-fixture.json').write_text(json.dumps(data,ensure_ascii=False))
	assert frappe.get_doc('Quotation',source).as_json() == before
	return str(root)
