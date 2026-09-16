app_name = "an_truck"
app_title = "AN Truck"
app_publisher = "AN"
app_description = "Truck Import, VIN Tracking, Vehicle Costing, Sales, Delivery, Warranty, and After-Sales Management."
app_email = "an@example.com"
app_license = "mit"

# Apps
# ------------------

required_apps = ["erpnext"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "an_truck",
# 		"logo": "/assets/an_truck/logo.png",
# 		"title": "AN Truck",
# 		"route": "/an_truck",
# 		"has_permission": "an_truck.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = "/assets/an_truck/css/an_truck.css"
# app_include_js = "/assets/an_truck/js/an_truck.js"

# include js, css files in header of web template
# web_include_css = "/assets/an_truck/css/an_truck.css"
# web_include_js = "/assets/an_truck/js/an_truck.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "an_truck/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	"Vehicle Import File": "public/js/vehicle_import_file.js",
	"Purchase Order": "public/js/purchase_order.js",
	"Purchase Receipt": "public/js/purchase_receipt.js",
	"Purchase Invoice": "public/js/purchase_invoice.js",
	"Landed Cost Voucher": "public/js/landed_cost_voucher.js",
	"Payment Entry": "public/js/payment_entry.js",
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "an_truck/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
role_home_page = {
	"AN Truck Manager": "/desk/an-truck-portal",
	"AN Truck Import User": "/desk/an-truck-portal",
	"AN Truck Receiving User": "/desk/an-truck-portal",
	"AN Truck Viewer": "/desk/an-truck-portal",
}

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "an_truck.utils.jinja_methods",
# 	"filters": "an_truck.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "an_truck.install.before_install"
# after_install = "an_truck.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "an_truck.uninstall.before_uninstall"
# after_uninstall = "an_truck.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "an_truck.utils.before_app_install"
# after_app_install = "an_truck.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "an_truck.utils.before_app_uninstall"
# after_app_uninstall = "an_truck.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "an_truck.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "an_truck.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Purchase Order": {
		"validate": "an_truck.services.validate_import_file_for_purchase_doc",
	},
	"Purchase Receipt": {
		"before_validate": "an_truck.services.before_validate_purchase_receipt",
		"on_submit": "an_truck.services.on_submit_purchase_receipt",
		"on_cancel": "an_truck.services.on_cancel_purchase_receipt",
	},
	"Purchase Invoice": {
		"validate": "an_truck.services.validate_purchase_invoice",
	},
	"Landed Cost Voucher": {
		"validate": "an_truck.services.validate_landed_cost_voucher",
		"on_submit": "an_truck.services.on_landed_cost_change",
		"on_cancel": "an_truck.services.on_landed_cost_change",
	},
	"Payment Entry": {
		"validate": "an_truck.services.validate_payment_entry",
	},
	"Vehicle": {
		"validate": "an_truck.services.validate_vehicle_registration",
	},
	"Sales Order": {
		"on_submit": "an_truck.services.on_submit_sales_order",
		"on_cancel": "an_truck.services.on_cancel_sales_order",
	},
	"Delivery Note": {
		"on_submit": "an_truck.services.on_submit_delivery_note",
		"on_cancel": "an_truck.services.on_cancel_delivery_note",
	},
	"Sales Invoice": {
		"on_submit": "an_truck.services.on_submit_sales_invoice",
		"on_cancel": "an_truck.services.on_cancel_sales_invoice",
	},
}

fixtures = [
	{
		"dt": "Custom Field",
		"filters": [["name", "in", [
			"Purchase Order-custom_vehicle_import_file",
			"Purchase Receipt-custom_vehicle_import_file",
			"Purchase Invoice-custom_vehicle_import_file",
			"Landed Cost Voucher-custom_vehicle_import_file",
			"Payment Entry-custom_vehicle_import_file",
			"Quotation-custom_vehicle_import_file",
			"Sales Order-custom_vehicle_import_file",
			"Delivery Note-custom_vehicle_import_file",
			"Sales Invoice-custom_vehicle_import_file",
			"Quotation Item-custom_vehicle_master",
			"Quotation Item-custom_vin",
			"Quotation Item-custom_vehicle_import_file",
			"Sales Order Item-custom_vehicle_master",
			"Sales Order Item-custom_vin",
			"Sales Order Item-custom_vehicle_import_file",
			"Delivery Note Item-custom_vehicle_master",
			"Delivery Note Item-custom_vin",
			"Delivery Note Item-custom_vehicle_import_file",
			"Sales Invoice Item-custom_vehicle_master",
			"Sales Invoice Item-custom_vin",
			"Sales Invoice Item-custom_vehicle_import_file",
			"Vehicle-custom_vehicle_import_file",
			"Vehicle-custom_vehicle_master",
			"Vehicle-custom_vin",
			"Vehicle-custom_registration_status",
		]]],
	},
]

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"an_truck.tasks.all"
# 	],
# 	"daily": [
# 		"an_truck.tasks.daily"
# 	],
# 	"hourly": [
# 		"an_truck.tasks.hourly"
# 	],
# 	"weekly": [
# 		"an_truck.tasks.weekly"
# 	],
# 	"monthly": [
# 		"an_truck.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "an_truck.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "an_truck.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "an_truck.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "an_truck.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["an_truck.utils.before_request"]
# after_request = ["an_truck.utils.after_request"]

# Job Events
# ----------
# before_job = ["an_truck.utils.before_job"]
# after_job = ["an_truck.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"an_truck.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
