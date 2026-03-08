# Scripts: linking products & deduplicating targets

## Linking products to companies

After running migration `002_targets_parent_for_products.sql`, product targets have a `parent_target_id` column. Until you set it, no products are associated with companies and the dashboard shows all products regardless of company.

## Option 1: Python script (recommended)

1. **List current targets** (so you can copy exact names):
   ```bash
   cd /path/to/product-sentiment-engine
   PYTHONPATH=src python scripts/link_products_to_companies.py --list
   ```

2. **Edit** `scripts/link_products_to_companies.py` and fill in the `PRODUCT_TO_COMPANY` dict with exact names from the list, e.g.:
   ```python
   PRODUCT_TO_COMPANY = {
       "MacBook Neo and iPhone 17e": "Apple",
       "Amazon Connect Health": "AWS",
   }
   ```

3. **Preview** (no DB writes):
   ```bash
   PYTHONPATH=src python scripts/link_products_to_companies.py --dry-run
   ```

4. **Apply**:
   ```bash
   PYTHONPATH=src python scripts/link_products_to_companies.py
   ```

## Option 2: SQL in Supabase

In Supabase → SQL Editor, run something like (replace names/IDs with your actual data):

```sql
-- First, see your targets:
SELECT id, name, target_type FROM targets ORDER BY target_type, name;

-- Then update by name (example: link product "MacBook Neo" to company "Apple"):
UPDATE targets
SET parent_target_id = (SELECT id FROM targets WHERE name = 'Apple' AND target_type = 'COMPANY' LIMIT 1)
WHERE target_type = 'PRODUCT' AND name = 'MacBook Neo';

-- Or update by ID (example: product id 5 → company id 2):
UPDATE targets SET parent_target_id = 2 WHERE id = 5;
```

Run one `UPDATE` per product you want to link.

---

## Reducing repetitive targets (similar naming)

Names like "M4 iPad Air" vs "iPad Air M4" or "Fire TV app" vs "Fire TV app (redesigned)" create duplicate targets. Two mechanisms help:

### 1) Prevention (Scout)

Scout now normalizes names before deciding if a target already exists: it strips parentheticals and sorts words, so new extractions that match an existing normalized name add an **event** to the existing target instead of creating a new one.

### 2) Find and merge existing duplicates

**Find groups** that share the same normalized name:

```bash
PYTHONPATH=src python scripts/find_duplicate_targets.py
```

**Merge** a duplicate into the canonical target (events and sentiment are reassigned, duplicate target is deleted):

```bash
# Preview
PYTHONPATH=src python scripts/merge_duplicate_targets.py --merge CANONICAL_ID DUPLICATE_ID --dry-run

# Apply (example: keep 41 "M4 iPad Air", merge 92 "iPad Air M4" into it)
PYTHONPATH=src python scripts/merge_duplicate_targets.py --merge 41 92
```

You can pass multiple `--merge K D` pairs in one run. Pick the canonical ID (the name you want to keep); the other will be removed after its data is moved.
