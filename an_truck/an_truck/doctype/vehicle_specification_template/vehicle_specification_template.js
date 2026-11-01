const specification_api = "an_truck.an_truck.doctype.vehicle_specification_template.vehicle_specification_template.";

frappe.ui.form.on("Vehicle Specification Template", {
	refresh(frm) {
		const immutable = !!frm.doc.published_on;
		const permanentReadOnly = new Set(["status", "revision", "revised_from", "published_on", "published_by"]);
		for (const field of frm.meta.fields) {
			if (!["Section Break", "Column Break"].includes(field.fieldtype) && !["active", "status"].includes(field.fieldname)) {
				frm.set_df_property(field.fieldname, "read_only", immutable || permanentReadOnly.has(field.fieldname));
			}
		}
		if (frm.is_new()) return;
		if (frm.doc.status === "Draft" && frm.perm[0]?.write) {
			frm.add_custom_button(__("Publish Template"), async () => {
				if (frm.is_dirty()) await frm.save();
				await frappe.call({ method: specification_api + "publish_template", args: { name: frm.doc.name } });
				await frm.reload_doc();
			});
		}
		if (frm.doc.status === "Published" && frappe.model.can_create("Vehicle Specification Template")) {
			frm.add_custom_button(__("Create New Revision"), async () => {
				const { message } = await frappe.call({ method: specification_api + "create_revision", args: { name: frm.doc.name } });
				frappe.set_route("Form", "Vehicle Specification Template", message.name);
			});
		}
		if (frappe.model.can_read("Vehicle Master")) {
			frappe.call({ method: specification_api + "get_linked_vehicle_count", args: { template: frm.doc.name } }).then(({ message }) => {
				if (frm.doc.name) frm.add_custom_button(`${__("View Linked Vehicles")} (${message || 0})`, () => show_linked_vehicles(frm.doc.name));
			});
		}
	},
});

function show_linked_vehicles(template) {
	let page = 1, generation = 0, timer;
	const dialog = new frappe.ui.Dialog({ title: __("Linked Vehicles"), size: "extra-large", fields: [
		{ fieldname: "search", fieldtype: "Data", label: __("Search by VIN, color or engine serial number"), onchange: reset },
		{ fieldtype: "Column Break" },
		{ fieldname: "status", fieldtype: "Select", label: __("Vehicle Status"), options: "", onchange: reset },
		{ fieldtype: "Section Break" },
		{ fieldname: "vehicles", fieldtype: "HTML" },
	] });
	function reset() { page = 1; clearTimeout(timer); timer = setTimeout(load, 250); }
	async function load() {
		const request = ++generation;
		const wrapper = dialog.fields_dict.vehicles.$wrapper;
		wrapper.text(__("Loading…"));
		try {
			const { message: data } = await frappe.call({ method: specification_api + "get_linked_vehicles", args: { template, search: dialog.get_value("search"), status: dialog.get_value("status"), page } });
			if (request !== generation) return;
			const esc = value => frappe.utils.escape_html(String(value ?? "—"));
			const statusField = dialog.fields_dict.status;
			statusField.df.options = ["", ...data.statuses].join("\n"); statusField.refresh();
			const labels = ["VIN / Chassis Number", "Color", "Vehicle Status", "Engine Serial Number", "Receipt Date", "Company", "Actions"];
			wrapper.html(`<div class="table-responsive"><table class="table table-bordered"><thead><tr>${labels.map(label => `<th>${esc(__(label))}</th>`).join("")}</tr></thead><tbody>${data.rows.length ? data.rows.map((row, index) => `<tr><td><bdi>${esc(row.vin)}</bdi></td><td>${esc(row.color)}</td><td>${esc(__(row.vehicle_status))}</td><td><bdi>${esc(row.engine_number)}</bdi></td><td>${esc(row.receipt_date)}</td><td>${esc(row.company)}</td><td><button class="btn btn-default btn-xs" data-vehicle="${index}">${esc(__("View Vehicle"))}</button></td></tr>`).join("") : `<tr><td colspan="7">${esc(__("No linked vehicles found."))}</td></tr>`}</tbody></table></div><div class="flex justify-between"><span>${esc(__("Number of Vehicles"))}: ${data.total} · ${esc(__("Page"))} ${page}</span><div><button class="btn btn-default btn-sm" data-page="previous" ${page <= 1 ? "disabled" : ""}>${esc(__("Previous"))}</button> <button class="btn btn-default btn-sm" data-page="next" ${!data.has_more ? "disabled" : ""}>${esc(__("Next"))}</button></div></div>`);
			wrapper.find("[data-vehicle]").on("click", function () { dialog.hide(); frappe.set_route("Form", "Vehicle Master", data.rows[Number(this.dataset.vehicle)].name); });
			wrapper.find("[data-page]").on("click", function () { page += this.dataset.page === "next" ? 1 : -1; load(); });
		} catch (error) { wrapper.text(__("Unable to load linked vehicles.")); }
	}
	dialog.show(); load();
}
