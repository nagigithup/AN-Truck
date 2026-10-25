frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || !frappe.model.can_read("Vehicle Warranty")) return;
		frappe.call({ method: "an_truck.warranty.workflow.get_invoice_warranty_context", args: { sales_invoice: frm.doc.name },
			callback: ({ message }) => {
				if (!message?.vehicles?.length) return;
				const hasOpen = message.can_create && message.vehicles.some((row) => !row.existing_warranty);
				if (!hasOpen && !message.vehicles.some((row) => row.existing_warranty)) return;
				frm.add_custom_button(hasOpen ? __("Add Warranty / إضافة ضمان") : __("View Warranty"),
					() => show_warranty_dialog(frm, message), __("Warranty"));
			},
		});
	},
});

function show_warranty_dialog(frm, context) {
	const vehicles = context.can_create ? context.vehicles : context.vehicles.filter((row) => row.existing_warranty);
	const templates = context.templates;
	const dialog = new frappe.ui.Dialog({
		title: __("Add Warranty / إضافة ضمان"),
		fields: [
			{ fieldname: "vehicle_master", fieldtype: "Select", label: __("VIN / Chassis Number"), reqd: 1, options: vehicles.map((row) => row.vehicle_master) },
			{ fieldname: "summary", fieldtype: "HTML" },
			{ fieldname: "coverage_template", fieldtype: "Select", label: __("Warranty Package / Coverage Template"), reqd: 1, options: ["", ...templates.map((row) => row.name)] },
			{ fieldname: "warranty_start_date", fieldtype: "Date", label: __("Start Date"), reqd: 1 },
			{ fieldname: "duration", fieldtype: "Data", label: __("Duration"), read_only: 1 },
			{ fieldname: "warranty_expiry_date", fieldtype: "Date", label: __("Expiry Date"), read_only: 1 },
			{ fieldname: "warranty_provider", fieldtype: "Select", label: __("Warranty Provider"), hidden: 1 },
			{ fieldname: "provider_contract", fieldtype: "Select", label: __("Provider Contract"), hidden: 1 },
			{ fieldname: "notes", fieldtype: "Small Text", label: __("Notes") },
		],
		primary_action_label: __("Add Warranty / إضافة ضمان"),
		primary_action: async (values) => {
			const row = vehicles.find((entry) => entry.vehicle_master === values.vehicle_master);
			if (row.existing_warranty) {
				dialog.hide(); frappe.set_route("Form", "Vehicle Warranty", row.existing_warranty); return;
			}
			const { message } = await frappe.call({ method: "an_truck.warranty.workflow.create_warranty_from_invoice",
				args: { sales_invoice: frm.doc.name, vehicle_master: values.vehicle_master,
					coverage_template: values.coverage_template, warranty_start_date: values.warranty_start_date,
					warranty_provider: values.warranty_provider, provider_contract: values.provider_contract,
					notes: values.notes }, freeze: true });
			dialog.hide();
			frappe.show_alert({ message: __("Vehicle Warranty {0} created.", [message.name]), indicator: "green" });
			frm.reload_doc();
		},
	});
	async function configure() {
		const values = dialog.get_values(true) || {};
		const row = vehicles.find((entry) => entry.vehicle_master === values.vehicle_master);
		if (!row) return;
		dialog.fields_dict.summary.$wrapper.html(`<div class="form-message blue"><b>${frappe.utils.escape_html(row.vehicle.label || row.vin)}</b><br>${frappe.utils.escape_html(row.customer.label || "")}</div>`);
		if (!(values.coverage_template && values.warranty_start_date) || row.existing_warranty) return;
		const { message } = await frappe.call({ method: "an_truck.warranty.workflow.get_warranty_configuration", args: {
			vehicle_master: row.vehicle_master, coverage_template: values.coverage_template,
			start_date: values.warranty_start_date, provider: values.warranty_provider || undefined } });
		const template = templates.find((entry) => entry.name === values.coverage_template);
		dialog.set_value("duration", template ? `${template.duration} ${__(template.duration_unit)}` : "");
		dialog.set_value("warranty_expiry_date", message.expiry_date);
		const providerField = dialog.fields_dict.warranty_provider;
		providerField.df.options = ["", ...message.providers]; providerField.refresh(); providerField.toggle(message.providers.length > 1);
		if (message.provider) dialog.set_value("warranty_provider", message.provider);
		const contractField = dialog.fields_dict.provider_contract;
		contractField.df.options = ["", ...message.contracts.map((entry) => entry.name)]; contractField.refresh(); contractField.toggle(message.contracts.length > 1);
		if (message.contract) dialog.set_value("provider_contract", message.contract);
	}
	dialog.fields_dict.vehicle_master.df.onchange = () => {
		const row = vehicles.find((entry) => entry.vehicle_master === dialog.get_value("vehicle_master"));
		dialog.set_value("warranty_start_date", row?.start_date || ""); configure();
	};
	for (const fieldname of ["coverage_template", "warranty_start_date", "warranty_provider"]) dialog.fields_dict[fieldname].df.onchange = configure;
	dialog.show(); dialog.set_value("vehicle_master", vehicles[0].vehicle_master);
}
