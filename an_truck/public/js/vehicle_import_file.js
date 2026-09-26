frappe.ui.form.on("Vehicle Import File", {
	refresh(frm) {
		if (frm.is_new()) return;
		prepare_unified_layout(frm);
		load_unified_screen(frm);
		frm.add_custom_button(__("Refresh Totals"), () => refresh_totals(frm));
	},
});

function prepare_unified_layout(frm) {
	frm.$wrapper.addClass("an-truck-form");
	if (frm.dashboard?.wrapper) {
		frm.dashboard.wrapper.hide();
	}
}

function load_unified_screen(frm) {
	frappe.call({
		method: "an_truck.transactions.get_unified_screen_data",
		args: { vehicle_import_file: frm.doc.name },
		callback(r) {
			frm.an_truck_data = r.message || {};
			render_control_panel(frm);
			render_transaction_lists(frm);
			render_summary(frm);
		},
	});
}

function render_control_panel(frm) {
	const wrapper = frm.fields_dict.transaction_control_panel_html?.$wrapper;
	if (!wrapper) return;
	const summary = frm.an_truck_data?.summary || {};
	wrapper.html(`
		<div class="an-truck-ops">
			<div class="an-truck-hero">
				<div>
					<div class="an-truck-kicker">${__("Unified Transaction Screen")}</div>
					<h3>${frappe.utils.escape_html(frm.doc.import_title || frm.doc.name)}</h3>
					<p>${frappe.utils.escape_html(frm.doc.supplier || "")} ${frm.doc.contract_number ? "&middot; " + frappe.utils.escape_html(frm.doc.contract_number) : ""}</p>
				</div>
				<div class="an-truck-status-badge">${frappe.utils.escape_html(summary.status || frm.doc.status || "")}</div>
			</div>
			<div class="an-truck-summary an-truck-summary-ops">
				<div><strong>${__("Expected")}</strong><span>${summary.expected || 0}</span></div>
				<div><strong>${__("Received")}</strong><span>${summary.received || 0}</span></div>
				<div><strong>${__("Remaining")}</strong><span>${summary.remaining || 0}</span></div>
				<div><strong>${__("Created Vehicle Masters")}</strong><span>${summary.created || 0}</span></div>
				<div><strong>${__("Contract Amount")}</strong><span>${format_currency(summary.contract_amount || 0, summary.currency)}</span></div>
			</div>
		</div>
	`);
}

function render_summary(frm) {
	const wrapper = frm.fields_dict.vehicle_summary_html?.$wrapper;
	if (!wrapper) return;
	wrapper.empty();
}

function render_transaction_lists(frm) {
	const wrapper = frm.fields_dict.transaction_lists_html?.$wrapper;
	if (!wrapper) return;
	const docs = frm.an_truck_data?.documents || {};
	const vehicles = frm.an_truck_data?.vehicles || [];
	wrapper.html(`
		<div class="an-truck-lists">
			${render_doc_group(__("Purchasing"), [
				[__("Purchase Orders"), docs.purchase_orders],
				[__("Purchase Receipts"), docs.purchase_receipts],
				[__("Purchase Invoices"), docs.purchase_invoices],
				[__("Supplier Payments"), docs.supplier_payments],
				[__("Landed Cost Vouchers"), docs.landed_cost_vouchers],
			])}
			${render_vehicle_group(vehicles)}
			${render_doc_group(__("Sales"), [
				[__("Quotations"), docs.quotations],
				[__("Sales Orders"), docs.sales_orders],
				[__("Delivery Notes"), docs.delivery_notes],
				[__("Sales Invoices"), docs.sales_invoices],
				[__("Customer Payments"), docs.customer_payments],
			])}
		</div>
	`);
}

function render_doc_group(title, sections) {
	return `<section class="an-truck-list-section"><h4>${title}</h4>${sections.map(([label, rows]) => render_doc_table(label, rows || [])).join("")}</section>`;
}

function render_doc_table(label, rows) {
	const body = rows.length ? rows.map((row) => `
		<tr>
			<td>${display_value(row.name)}</td>
			<td>${frappe.datetime.str_to_user(row.date || "")}</td>
			<td>${frappe.utils.escape_html(row.party || "")}</td>
			<td>${frappe.utils.escape_html(row.currency || "")}</td>
			<td class="text-right">${format_currency(row.amount || 0, row.currency)}</td>
			<td>${frappe.utils.escape_html(row.status || docstatus_label(row.docstatus))}</td>
			<td class="text-right">${row.outstanding_amount == null ? "" : format_currency(row.outstanding_amount, row.currency)}</td>
		</tr>
	`).join("") : `<tr><td colspan="7" class="text-muted">${__("No records")}</td></tr>`;
	return `<h5>${label}</h5><table class="table table-bordered table-condensed an-truck-table">
		<thead><tr><th>${__("Document Number")}</th><th>${__("Date")}</th><th>${__("Party")}</th><th>${__("Currency")}</th><th>${__("Amount")}</th><th>${__("Status")}</th><th>${__("Outstanding Amount")}</th></tr></thead>
		<tbody>${body}</tbody>
	</table>`;
}

function render_vehicle_group(vehicles) {
	const body = vehicles.length ? vehicles.map((row) => `
		<tr>
			<td>${display_value(row.vin || row.name)}</td>
			<td>${frappe.utils.escape_html(row.item_code || "")}</td>
			<td>${frappe.utils.escape_html(row.model || "")}</td>
			<td>${frappe.utils.escape_html(row.color || "")}</td>
			<td>${frappe.utils.escape_html(row.warehouse || "")}</td>
			<td>${frappe.utils.escape_html(row.vehicle_status || "")}</td>
			<td class="text-right">${format_currency(row.final_valuation_rate || 0)}</td>
			<td class="text-right">${format_currency(row.selling_rate || 0)}</td>
		</tr>
	`).join("") : `<tr><td colspan="8" class="text-muted">${__("No vehicles")}</td></tr>`;
	return `<section class="an-truck-list-section"><h4>${__("Vehicles")}</h4><table class="table table-bordered table-condensed an-truck-table">
		<thead><tr><th>${__("VIN")}</th><th>${__("Item Code")}</th><th>${__("Model")}</th><th>${__("Color")}</th><th>${__("Warehouse")}</th><th>${__("Vehicle Status")}</th><th>${__("Final Valuation Rate")}</th><th>${__("Selling Rate")}</th></tr></thead>
		<tbody>${body}</tbody>
	</table></section>`;
}

function display_value(value) {
	return `<span>${frappe.utils.escape_html(value || "")}</span>`;
}

function docstatus_label(docstatus) {
	return [__("Draft"), __("Submitted"), __("Cancelled")][docstatus || 0];
}

function call_transaction(frm, dialog, method, values, success_label) {
	const primary = dialog.get_primary_btn();
	primary.prop("disabled", true);
	frappe.call({
		method,
		args: {
			vehicle_import_file: frm.doc.name,
			data: values,
			submit_now: values.submit_now ? 1 : 0,
			idempotency_key: frappe.utils.get_random(12),
		},
		callback(r) {
			if (!r.message) return;
			dialog.hide();
			frappe.show_alert({
				message: `${success_label}: ${frappe.utils.escape_html(r.message.name)}`,
				indicator: "green",
			});
			frm.reload_doc().then(() => load_unified_screen(frm));
		},
		always() {
			primary.prop("disabled", false);
		},
	});
}

function show_purchase_order_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Create Purchase Order"),
		size: "extra-large",
		fields: [
			{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frm.doc.company, read_only: 1 },
			{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier", default: frm.doc.supplier, read_only: 1 },
			{ fieldname: "currency", label: __("Currency"), fieldtype: "Link", options: "Currency", default: frm.doc.supplier_currency, read_only: 1 },
			{ fieldname: "contract_number", label: __("Contract Number"), fieldtype: "Data", default: frm.doc.contract_number, read_only: 1 },
			{ fieldname: "required_by_date", label: __("Required By Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.nowdate() },
			{ fieldname: "supplier_quotation_number", label: __("Supplier Quotation Number"), fieldtype: "Data" },
			{ fieldname: "supplier_quotation_date", label: __("Supplier Quotation Date"), fieldtype: "Date" },
			{ fieldname: "taxes_template", label: __("Taxes Template"), fieldtype: "Link", options: "Purchase Taxes and Charges Template" },
			{ fieldname: "notes", label: __("Notes"), fieldtype: "Small Text" },
			{ fieldname: "items", label: __("Items"), fieldtype: "Table", reqd: 1, cannot_add_rows: false, in_place_edit: true, fields: purchase_item_fields() },
			{ fieldname: "submit_now", label: __("Submit Now"), fieldtype: "Check" },
		],
		primary_action_label: __("Confirm"),
		primary_action(values) {
			call_transaction(frm, dialog, "an_truck.transactions.create_purchase_order", values, __("Purchase Order created"));
		},
	});
	dialog.show();
}

function purchase_item_fields() {
	return [
		{ fieldname: "item_code", label: __("Item Code"), fieldtype: "Link", options: "Item", in_list_view: 1, reqd: 1 },
		{ fieldname: "item_name", label: __("Item Name"), fieldtype: "Data", in_list_view: 1, read_only: 1 },
		{ fieldname: "description", label: __("Description"), fieldtype: "Small Text" },
		{ fieldname: "qty", label: __("Quantity"), fieldtype: "Float", in_list_view: 1, reqd: 1 },
		{ fieldname: "uom", label: __("UOM"), fieldtype: "Link", options: "UOM" },
		{ fieldname: "rate", label: __("Rate"), fieldtype: "Currency", in_list_view: 1 },
		{ fieldname: "amount", label: __("Amount"), fieldtype: "Currency", in_list_view: 1, read_only: 1 },
		{ fieldname: "schedule_date", label: __("Schedule Date"), fieldtype: "Date" },
		{ fieldname: "warehouse", label: __("Warehouse"), fieldtype: "Link", options: "Warehouse", in_list_view: 1 },
	];
}

function show_purchase_receipt_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Record Purchase Receipt"),
		size: "extra-large",
		fields: [
			{ fieldname: "purchase_order", label: __("Purchase Order"), fieldtype: "Link", options: "Purchase Order", reqd: 1, get_query: () => ({ filters: { custom_vehicle_import_file: frm.doc.name, docstatus: 1 } }) },
			{ fieldname: "posting_date", label: __("Posting Date"), fieldtype: "Date", default: frappe.datetime.nowdate() },
			{ fieldname: "items", label: __("Items"), fieldtype: "Table", cannot_add_rows: true, in_place_edit: true, fields: receipt_item_fields() },
			{ fieldname: "vins", label: __("VIN numbers"), fieldtype: "Table", cannot_add_rows: false, in_place_edit: true, fields: vin_fields() },
			{ fieldname: "submit_now", label: __("Submit Receipt"), fieldtype: "Check" },
		],
		primary_action_label: __("Confirm"),
		primary_action(values) {
			call_transaction(frm, dialog, "an_truck.transactions.create_purchase_receipt", values, __("Purchase Receipt created"));
		},
	});
	dialog.fields_dict.purchase_order.df.onchange = () => {
		const po = dialog.get_value("purchase_order");
		if (!po) return;
		frappe.call({
			method: "an_truck.transactions.get_purchase_order_items",
			args: { purchase_order: po, vehicle_import_file: frm.doc.name },
			callback(r) {
				dialog.set_value("items", r.message || []);
			},
		});
	};
	dialog.show();
}

function receipt_item_fields() {
	return [
		{ fieldname: "purchase_order_item", label: __("PO Item"), fieldtype: "Data", hidden: 1 },
		{ fieldname: "item_code", label: __("Item Code"), fieldtype: "Link", options: "Item", in_list_view: 1, read_only: 1 },
		{ fieldname: "item_name", label: __("Item Name"), fieldtype: "Data", in_list_view: 1, read_only: 1 },
		{ fieldname: "ordered_qty", label: __("Ordered Quantity"), fieldtype: "Float", read_only: 1 },
		{ fieldname: "received_qty", label: __("Previously Received Quantity"), fieldtype: "Float", read_only: 1 },
		{ fieldname: "remaining_qty", label: __("Remaining Quantity"), fieldtype: "Float", in_list_view: 1, read_only: 1 },
		{ fieldname: "qty", label: __("Quantity to Receive"), fieldtype: "Float", in_list_view: 1 },
		{ fieldname: "warehouse", label: __("Target Warehouse"), fieldtype: "Link", options: "Warehouse", in_list_view: 1 },
	];
}

function vin_fields() {
	return [
		{ fieldname: "vin", label: __("VIN / Chassis Number"), fieldtype: "Data", in_list_view: 1, reqd: 1 },
		{ fieldname: "item_code", label: __("Item Code"), fieldtype: "Link", options: "Item", in_list_view: 1, reqd: 1 },
		{ fieldname: "model", label: __("Model"), fieldtype: "Data" },
		{ fieldname: "color", label: __("Color"), fieldtype: "Data" },
		{ fieldname: "engine_number", label: __("Engine Number"), fieldtype: "Data" },
		{ fieldname: "notes", label: __("Notes"), fieldtype: "Small Text" },
	];
}

function show_purchase_invoice_dialog(frm) {
	show_source_dialog(frm, __("Create Purchase Invoice"), [
		["Purchase Order", "Purchase Order"],
		["Purchase Receipt", "Purchase Receipt"],
	], "an_truck.transactions.create_purchase_invoice", __("Purchase Invoice created"), [
		{ fieldname: "supplier_invoice_number", label: __("Supplier Invoice Number"), fieldtype: "Data", reqd: 1 },
		{ fieldname: "supplier_invoice_date", label: __("Supplier Invoice Date"), fieldtype: "Date", reqd: 1 },
		{ fieldname: "posting_date", label: __("Posting Date"), fieldtype: "Date", default: frappe.datetime.nowdate() },
		{ fieldname: "due_date", label: __("Due Date"), fieldtype: "Date" },
		{ fieldname: "exchange_rate", label: __("Exchange Rate"), fieldtype: "Float" },
		{ fieldname: "taxes_template", label: __("Taxes Template"), fieldtype: "Link", options: "Purchase Taxes and Charges Template" },
		{ fieldname: "remarks", label: __("Remarks"), fieldtype: "Small Text" },
	]);
}

function show_payment_dialog(frm, reference_doctype) {
	const is_purchase = reference_doctype === "Purchase Invoice";
	show_source_dialog(frm, is_purchase ? __("Record Supplier Payment") : __("Record Customer Payment"), [[reference_doctype, reference_doctype]], "an_truck.transactions.create_payment_entry", __("Payment Entry created"), [
		{ fieldname: "posting_date", label: __("Posting Date"), fieldtype: "Date", default: frappe.datetime.nowdate() },
		{ fieldname: "paid_from_account", label: __("Paid From Account"), fieldtype: "Link", options: "Account", hidden: !is_purchase },
		{ fieldname: "paid_to_account", label: __("Paid To Account"), fieldtype: "Link", options: "Account", hidden: !is_purchase },
		{ fieldname: "received_to_account", label: __("Received To Account"), fieldtype: "Link", options: "Account", hidden: is_purchase },
		{ fieldname: "paid_amount", label: __("Paid Amount"), fieldtype: "Currency", reqd: 1 },
		{ fieldname: "mode_of_payment", label: __("Mode of Payment"), fieldtype: "Link", options: "Mode of Payment" },
		{ fieldname: "reference_number", label: __("Reference Number"), fieldtype: "Data" },
		{ fieldname: "reference_date", label: __("Reference Date"), fieldtype: "Date" },
		{ fieldname: "remarks", label: __("Remarks"), fieldtype: "Small Text" },
	]);
}

function show_landed_cost_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Landed Cost"),
		size: "large",
		fields: [
			{ fieldname: "posting_date", label: __("Posting Date"), fieldtype: "Date", default: frappe.datetime.nowdate() },
			{ fieldname: "allocation_basis", label: __("Allocation Basis"), fieldtype: "Select", options: "Qty\nAmount\nWeight", default: "Qty" },
			{ fieldname: "purchase_receipts", label: __("Purchase Receipts"), fieldtype: "Table", fields: [{ fieldname: "receipt_document", label: __("Purchase Receipt"), fieldtype: "Link", options: "Purchase Receipt", in_list_view: 1, reqd: 1 }] },
			{ fieldname: "taxes", label: __("Additional Costs"), fieldtype: "Table", fields: [
				{ fieldname: "description", label: __("Expense Description"), fieldtype: "Data", in_list_view: 1, reqd: 1 },
				{ fieldname: "expense_account", label: __("Expense Account"), fieldtype: "Link", options: "Account", in_list_view: 1 },
				{ fieldname: "amount", label: __("Amount"), fieldtype: "Currency", in_list_view: 1, reqd: 1 },
				{ fieldname: "currency", label: __("Currency"), fieldtype: "Link", options: "Currency" },
				{ fieldname: "exchange_rate", label: __("Exchange Rate"), fieldtype: "Float" },
			] },
			{ fieldname: "submit_now", label: __("Submit Now"), fieldtype: "Check" },
		],
		primary_action_label: __("Confirm"),
		primary_action(values) {
			call_transaction(frm, dialog, "an_truck.transactions.create_landed_cost_voucher", values, __("Landed Cost Voucher created"));
		},
	});
	dialog.show();
}

function show_quotation_dialog(frm) {
	show_vehicle_sales_dialog(frm, __("Create Customer Quotation"), "an_truck.transactions.create_customer_quotation", __("Quotation created"), false);
}

function show_sales_order_dialog(frm) {
	show_vehicle_sales_dialog(frm, __("Create Sales Order"), "an_truck.transactions.create_sales_order", __("Sales Order created"), true);
}

function show_vehicle_sales_dialog(frm, title, method, success_label, needs_delivery_date) {
	const dialog = new frappe.ui.Dialog({
		title,
		size: "large",
		fields: [
			{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer", reqd: 1 },
			{ fieldname: "currency", label: __("Transaction Currency"), fieldtype: "Link", options: "Currency" },
			{ fieldname: "exchange_rate", label: __("Exchange Rate"), fieldtype: "Float" },
			{ fieldname: "delivery_date", label: __("Delivery Date"), fieldtype: "Date", default: frappe.datetime.nowdate(), reqd: needs_delivery_date },
			{ fieldname: "price_list", label: __("Price List"), fieldtype: "Link", options: "Price List" },
			{ fieldname: "vehicles", label: __("Vehicles"), fieldtype: "Table", fields: [{ fieldname: "vehicle_master", label: __("Vehicle Master"), fieldtype: "Link", options: "Vehicle Master", in_list_view: 1, reqd: 1 }] },
			{ fieldname: "submit_now", label: needs_delivery_date ? __("Submit Sales Order") : __("Submit Now"), fieldtype: "Check" },
		],
		primary_action_label: __("Confirm"),
		primary_action(values) {
			call_transaction(frm, dialog, method, values, success_label);
		},
	});
	dialog.show();
}

function show_delivery_note_dialog(frm) {
	show_source_dialog(frm, __("Create Delivery Note"), [["Sales Order", "Sales Order"]], "an_truck.transactions.create_delivery_note", __("Delivery Note created"), [
		{ fieldname: "posting_date", label: __("Posting Date"), fieldtype: "Date", default: frappe.datetime.nowdate() },
		{ fieldname: "source_warehouse", label: __("Source Warehouse"), fieldtype: "Link", options: "Warehouse" },
		{ fieldname: "vehicles", label: __("Vehicle VINs"), fieldtype: "Table", fields: [{ fieldname: "vehicle_master", label: __("Vehicle Master"), fieldtype: "Link", options: "Vehicle Master", in_list_view: 1 }] },
	], { source_fieldname: "sales_order" });
}

function show_sales_invoice_dialog(frm) {
	show_source_dialog(frm, __("Create Sales Invoice"), [["Sales Order", "Sales Order"], ["Delivery Note", "Delivery Note"]], "an_truck.transactions.create_sales_invoice", __("Sales Invoice created"), [
		{ fieldname: "posting_date", label: __("Posting Date"), fieldtype: "Date", default: frappe.datetime.nowdate() },
		{ fieldname: "due_date", label: __("Due Date"), fieldtype: "Date" },
		{ fieldname: "exchange_rate", label: __("Exchange Rate"), fieldtype: "Float" },
		{ fieldname: "taxes_template", label: __("Taxes Template"), fieldtype: "Link", options: "Sales Taxes and Charges Template" },
		{ fieldname: "remarks", label: __("Remarks"), fieldtype: "Small Text" },
	]);
}

function show_source_dialog(frm, title, sources, method, success_label, extra_fields, options = {}) {
	const source_options = sources.map((row) => row[0]).join("\n");
	const source_fieldname = options.source_fieldname || "source_name";
	const dialog = new frappe.ui.Dialog({
		title,
		size: "large",
		fields: [
			{ fieldname: "source_type", label: __("Source Document Type"), fieldtype: "Select", options: source_options, default: sources[0][0], reqd: !options.source_fieldname },
			{ fieldname: source_fieldname, label: __("Source Document"), fieldtype: "Dynamic Link", options: "source_type", reqd: 1, get_query: () => ({ filters: { custom_vehicle_import_file: frm.doc.name, docstatus: 1 } }) },
			...extra_fields,
			{ fieldname: "submit_now", label: __("Submit Now"), fieldtype: "Check" },
		],
		primary_action_label: __("Confirm"),
		primary_action(values) {
			if (options.source_fieldname) {
				values.source_type = sources[0][0];
				values.source_name = values[source_fieldname];
			}
			values.reference_doctype = values.source_type;
			values.reference_name = values.source_name;
			call_transaction(frm, dialog, method, values, success_label);
		},
	});
	dialog.show();
}

function show_vehicle_info_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Complete Vehicle Information"),
		size: "extra-large",
		fields: [{ fieldname: "vehicles", label: __("Vehicles"), fieldtype: "Table", fields: [
			{ fieldname: "name", label: __("Vehicle Master"), fieldtype: "Link", options: "Vehicle Master", in_list_view: 1, reqd: 1 },
			{ fieldname: "brand", label: __("Brand"), fieldtype: "Data" },
			{ fieldname: "model", label: __("Model"), fieldtype: "Data", in_list_view: 1 },
			{ fieldname: "model_year", label: __("Model Year"), fieldtype: "Int" },
			{ fieldname: "color", label: __("Color"), fieldtype: "Data", in_list_view: 1 },
			{ fieldname: "engine_number", label: __("Engine Number"), fieldtype: "Data" },
			{ fieldname: "notes", label: __("Notes"), fieldtype: "Small Text" },
		] }],
		primary_action_label: __("Confirm"),
		primary_action(values) {
			frappe.call({
				method: "an_truck.transactions.complete_vehicle_information",
				args: { vehicle_import_file: frm.doc.name, data: values },
				callback() {
					dialog.hide();
					frm.reload_doc().then(() => load_unified_screen(frm));
				},
			});
		},
	});
	dialog.show();
}

function show_inspection_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Start Vehicle Inspection"),
		fields: [{ fieldname: "vehicles", label: __("Vehicles"), fieldtype: "Table", fields: [{ fieldname: "vehicle_master", label: __("Vehicle Master"), fieldtype: "Link", options: "Vehicle Master", in_list_view: 1, reqd: 1 }] }],
		primary_action_label: __("Confirm"),
		primary_action(values) {
			frappe.call({
				method: "an_truck.transactions.start_vehicle_inspection",
				args: { vehicle_import_file: frm.doc.name, data: values },
				callback() {
					dialog.hide();
					frm.reload_doc().then(() => load_unified_screen(frm));
				},
			});
		},
	});
	dialog.show();
}

function refresh_totals(frm) {
	return frappe.call({
		method: "an_truck.an_truck.doctype.vehicle_import_file.vehicle_import_file.refresh_import_file_totals",
		args: { name: frm.doc.name },
		callback: () => frm.reload_doc().then(() => load_unified_screen(frm)),
	});
}
