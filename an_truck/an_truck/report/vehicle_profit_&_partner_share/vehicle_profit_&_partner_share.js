frappe.query_reports["Vehicle Profit & Partner Share"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Sale Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Sale Date"), fieldtype: "Date" },
		{ fieldname: "vin", label: __("VIN"), fieldtype: "Link", options: "Vehicle Master" },
		{ fieldname: "vehicle", label: __("Vehicle"), fieldtype: "Link", options: "Item" },
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
		{
			fieldname: "vehicle_import_file",
			label: __("Vehicle Import File"),
			fieldtype: "Link",
			options: "Vehicle Import File",
		},
		{
			fieldname: "vehicle_status",
			label: __("Vehicle Status"),
			fieldtype: "Select",
			options: "\nOrdered\nIn Transit\nReceived\nUnder Inspection\nAvailable\nReserved\nSold\nDelivered\nUnder Maintenance\nReceipt Cancelled",
		},
		{
			fieldname: "distribution_status",
			label: __("Profit Distribution Status"),
			fieldtype: "Select",
			options: "All\nNot Distributed\nDistributed",
			default: "Not Distributed",
		},
	],

	get_datatable_options(options) {
		return Object.assign(options, { checkboxColumn: true });
	},

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (["profit_loss", "chinese_share", "showroom_share"].includes(column.fieldname)) {
			const css_class = flt(data[column.fieldname]) < 0 ? "text-danger" : "text-success";
			return `<span class="${css_class}">${value}</span>`;
		}
		if (column.fieldname === "distribution_status") {
			const distributed = cint(data.profit_distributed) === 1;
			return `<span class="indicator-pill ${distributed ? "green" : "orange"}">${value}</span>`;
		}
		return value;
	},

	onload(report) {
		const allowed = ["System Manager", "AN Truck Manager"].some((role) =>
			(frappe.user_roles || []).includes(role)
		);
		if (!allowed) return;

		report.page.add_inner_button(__("Mark Profit Distributed"), () => {
			const indexes = frappe.query_report.datatable?.rowmanager?.getCheckedRows() || [];
			const selected_rows = indexes
				.map((index) => frappe.query_report.data[index])
				.filter((item) => item?.vehicle_master);

			if (!selected_rows.length) {
				frappe.throw(__("Please select at least one vehicle."));
			}

			const totals = selected_rows.reduce(
				(result, item) => {
					result.profit_loss += flt(item.profit_loss);
					result.chinese_share += flt(item.chinese_share);
					result.showroom_share += flt(item.showroom_share);
					return result;
				},
				{ profit_loss: 0, chinese_share: 0, showroom_share: 0 }
			);
			const currency = selected_rows.find((item) => item.cost_currency)?.cost_currency;
			const message = `
				<p>${__("Are you sure you want to record the profit/loss distribution for {0} vehicle(s)?", [selected_rows.length])}</p>
				<table class="table table-bordered table-condensed">
					<tr><td>${__("Total Profit / Loss")}</td><td class="text-end">${format_currency(totals.profit_loss, currency)}</td></tr>
					<tr><td>${__("Chinese Partner Share 49%")}</td><td class="text-end">${format_currency(totals.chinese_share, currency)}</td></tr>
					<tr><td>${__("Abu Turki / Showroom Share 51%")}</td><td class="text-end">${format_currency(totals.showroom_share, currency)}</td></tr>
				</table>`;

			frappe.confirm(message, () => {
				frappe.call({
					method: "an_truck.an_truck.report.vehicle_profit_and_partner_share.vehicle_profit_and_partner_share.mark_profit_distributed",
					args: { vehicle_names: selected_rows.map((item) => item.vehicle_master) },
					freeze: true,
					freeze_message: __("Recording profit distribution..."),
					callback(response) {
						if (!response.message) return;
						frappe.show_alert(
							{
								message: __("Profit distribution recorded successfully for {0} vehicle(s).", [response.message.count]),
								indicator: "green",
							},
							7
						);
						frappe.query_report.refresh();
					},
				});
			});
		});
	},
};
