// Copyright (c) 2026, AN and contributors
// For license information, please see license.txt

frappe.ui.form.on("Vehicle Master", {
	setup(frm) {
		frm.set_query("specification_template", () => ({
			query: "an_truck.an_truck.doctype.vehicle_specification_template.vehicle_specification_template.template_query",
			filters: { item_code: frm.doc.item_code },
		}));
	},
	refresh(frm) {
		frm.set_df_property("specification_template", "reqd", frm.is_new());
		frm.set_df_property("vin", "read_only", !frm.is_new());
		frm._confirmed_specification_template = frm.doc.specification_template || "";
		render_specifications(frm);
	},
	async specification_template(frm) {
		const previous = frm._confirmed_specification_template || "";
		const selected = frm.doc.specification_template || "";
		if (!frm.is_new() && previous !== selected && !frm._restoring_specification) {
			frappe.confirm(__("Change the specification template for this vehicle? VIN and vehicle-specific data will be preserved."), () => {
				frm._confirmed_specification_template = selected;
				render_specifications(frm);
			}, async () => {
				frm._restoring_specification = true;
				await frm.set_value("specification_template", previous);
				frm._restoring_specification = false;
			});
		} else render_specifications(frm);
	},
});

async function render_specifications(frm) {
	const wrapper = frm.fields_dict.template_specifications.$wrapper;
	wrapper.empty();
	if (!frm.doc.specification_template) { wrapper.text(__("No Specification Template linked.")); return; }
	const name = frm.doc.specification_template;
	const { message: doc } = await frappe.call({ method: "frappe.client.get", args: { doctype: "Vehicle Specification Template", name } });
	if (frm.doc.specification_template !== name) return;
	await frappe.model.with_doctype("Vehicle Specification Template");
	const esc = value => frappe.utils.escape_html(String(value ?? ""));
	const fields = frappe.get_meta("Vehicle Specification Template").fields.filter(field => !field.hidden && !["Section Break", "Column Break", "Table", "HTML"].includes(field.fieldtype) && !["published_on", "published_by", "revised_from"].includes(field.fieldname) && doc[field.fieldname]);
	wrapper.html(`<details><summary>${esc(__("Linked Technical Specifications"))} · ${esc(name)}</summary><div class="table-responsive"><table class="table table-bordered">${fields.map(field => `<tr><th>${esc(__(field.label))}</th><td>${esc(doc[field.fieldname])}</td></tr>`).join("")}${(doc.technical_specifications || []).map(row => `<tr><th>${esc(row.specification_name)}</th><td>${esc(row.value)} ${esc(row.uom)}</td></tr>`).join("")}</table></div></details>`);
}
