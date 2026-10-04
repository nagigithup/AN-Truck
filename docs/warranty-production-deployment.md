# Warranty Production Deployment and Rollback

This is a runbook only. Substitute the production bench, site, repository, and revision deliberately. Do not paste these commands without verifying each target.

## Preflight and backup

1. Confirm an approved maintenance window, administrator access, free disk space, database health, Redis/workers, and the correct site with `bench --site SITE list-apps`.
2. Record the current application revisions: `git -C apps/an_truck rev-parse HEAD`, `git -C apps/frappe rev-parse HEAD`, and `git -C apps/erpnext rev-parse HEAD`. Record the deployed release/tag outside the server.
3. Create database and file backups: `bench --site SITE backup --with-files`. Copy the resulting database, public-files, private-files, and encryption/config material to protected off-host storage. Verify files exist and are non-empty.
4. Take a separate infrastructure/database snapshot when the hosting platform supports it. Test restore procedure in staging before the production window.
5. Export the Historical Warranty Backfill Preview and Warranty Data Quality reports. Do not execute backfill as part of migration.

## Deployment

1. Put the production site in maintenance mode: `bench --site SITE set-maintenance-mode on`.
2. Fetch/checkout only the approved AN Truck revision through the organization's release procedure. Do not update Frappe/ERPNext unless included in the approved release.
3. Run `bench --site SITE migrate`.
4. Build assets with `bench build --app an_truck`.
5. Run `bench --site SITE clear-cache` and restart processes with the environment's process supervisor or `bench restart` where appropriate.
6. Verify scheduler state with `bench --site SITE scheduler status`; enable it only if production policy expects it: `bench --site SITE enable-scheduler`.
7. Disable maintenance mode: `bench --site SITE set-maintenance-mode off`.

## Smoke checks

- Login as Warranty Manager and open workspace, dashboard, Historical Backfill Preview, Data Quality, and one VIN history.
- Verify Company Warranty Processing Time Zone values, especially `Asia/Riyadh`; do not alter global timezone.
- Deliver a staging/test VIN through the approved production smoke-data process and verify activation, coverage snapshot, expiry, Serial No sync, claim totals, workflow, and certificate rendering.
- Login as fixed-branch and All Branches provider users; verify provider/branch isolation and private download authorization.
- Check workers, scheduler, Error Log, background jobs, web console, and asset responses.
- Review the two expiry milestones without sending customer messages.

## Backfill after deployment

1. Export and obtain business approval for the preview.
2. Resolve configuration-only blockers (provider/template/contract) through normal master-data approval. Do not manufacture missing delivery dates.
3. Execute READY records in a small Company/VIN-controlled batch as Warranty Manager/System Manager.
4. Review Created/Skipped/Failed/Manual Review, audit Comments, Serial No expiry, and Data Quality again. Save evidence.

## Rollback

Stop new writes and put the site back into maintenance mode. Capture logs and a post-failure backup before rollback if safe. Restore the exact pre-deployment code revision using the organization's non-destructive release mechanism, restore the database and both file archives from the matched pre-deployment backup, restore required site configuration/encryption material, then run the version-appropriate migrate/build/cache/restart steps. Never restore only the database or only files when warranty attachments may have changed.

Validate record counts, recent sales/delivery/VIN flows, private files, scheduler, and provider isolation before reopening. A rollback restores the entire backup point; business transactions created after that point require an approved reconciliation plan. Do not use destructive Git reset commands or ad-hoc SQL deletion as rollback.
