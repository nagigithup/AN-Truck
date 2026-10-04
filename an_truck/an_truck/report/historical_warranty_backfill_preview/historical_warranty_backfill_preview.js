frappe.query_reports["Historical Warranty Backfill Preview"] = {
	filters: [
		{fieldname:"company", label:__("Company"), fieldtype:"Link", options:"Company", default:frappe.defaults.get_user_default("Company")},
		{fieldname:"vin", label:__("VIN"), fieldtype:"Link", options:"Serial No"},
	],
	onload(report) {
		if (frappe.user.has_role(["System Manager", "AN Truck Warranty Manager"])) {
			report.page.add_inner_button(__("Execute READY Records"), () => {
				frappe.confirm(__("Create warranties for all records that are still READY after server revalidation?"), async () => {
					const filters = report.get_values();
					const {message} = await frappe.call({
						method:"an_truck.warranty.backfill.execute_historical_backfill",
						type:"POST", freeze:true, args:{company:filters.company, vin:filters.vin},
					});
					frappe.msgprint({title:__("Historical Warranty Backfill"), indicator:message.failed ? "orange" : "green",
						message:__("Eligible: {0}<br>Created: {1}<br>Skipped: {2}<br>Failed: {3}<br>Manual Review: {4}", [message.eligible,message.created,message.skipped,message.failed,message.manual_review])});
					report.refresh();
				});
			});
		}
	},
};
