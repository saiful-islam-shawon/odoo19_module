# Zencore Cold Storage Management (`zencore_cold_storage_management`)

**Module Name:** `zencore_cold_storage_management`  
**Odoo Version:** 19.0 (Community & Enterprise)  
**Category:** `GAPL`  
**License:** LGPL-3  
**Author:** Zencore / Antigravity AI  

---

## 1. Overview & Purpose
`zencore_cold_storage_management` provides complete operational season tracking and multi-tier physical warehouse location configuration for agricultural cold storage businesses (e.g., potato and fruit cold storage facilities).

---

## 2. Key Features

### Season Management (`REQ-001`)
* Dedicated root menu **Cold Storage Management** with submenus **Season** and **Configuration**.
* **Model:** `cold.storage.season`
* Tracks Season Name, Start Date, End Date, Default Bag Rate, Operational Team (`Char`), and Season Manager (`Char`).
* State workflow: `Draft` $\rightarrow$ `Open` $\rightarrow$ `Closed` $\rightarrow$ `Reset to Draft`.
* Python validations:
  * Ensures End Date is greater than or equal to Start Date.
  * Ensures Default Bag Rate is non-negative ($\ge 0$).
* Locked / Read-only fields when in `Closed` status.

### Physical Location Hierarchy & Master Setup (`REQ-002`)
* Four master models under **Configuration**:
  * **Chamber:** `cold.storage.chamber` (Unique name constraint)
  * **Floor:** `cold.storage.floor` (Unique name constraint)
  * **Line:** `cold.storage.line` (Unique name constraint)
  * **Pocket:** `cold.storage.pocket` (Unique name constraint)
* Central registry: **Storage Master Setup** (`cold.storage.master.setup`):
  * Links Chamber, Floor, Line, and Pocket with Many2one relations.
  * Computed stored display name: `"Chamber / Floor / Line / Pocket"`.
  * Operational toggle: `activate` (Boolean, default `False`).
  * 4-way SQL unique constraint: `unique(chamber_id, floor_id, line_id, pocket_id)`.

---

## 3. Security & Access Control
Odoo 19 security access rules defined in `security/ir.model.access.csv`:
* **Internal Users (`base.group_user`):** Read-only access (`perm_read=1`) to all cold storage models.
* **System Administrators (`base.group_system`):** Full CRUD access (`perm_read,perm_write,perm_create,perm_unlink=1`) to all cold storage models.

---

## 4. Local CLI Runbook

### Module Installation:
```bash
./venv/bin/python odoo/odoo-bin -c odoo.conf -d odoo_antigravity_test -i zencore_cold_storage_management --stop-after-init
```

### Module Upgrade:
```bash
./venv/bin/python odoo/odoo-bin -c odoo.conf -d odoo_antigravity_test -u zencore_cold_storage_management --stop-after-init
```

### Run Automated Tests:
```bash
./venv/bin/python odoo/odoo-bin -c odoo.conf -d odoo_antigravity_test --test-enable --test-tags /zencore_cold_storage_management --stop-after-init
```
