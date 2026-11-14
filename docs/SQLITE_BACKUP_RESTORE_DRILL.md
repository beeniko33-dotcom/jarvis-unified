# Paper ledger backup and restore drill

Run this against a **closed or concurrently quiescent** persistent paper-ledger database:

```bash
python scripts/sqlite_backup_restore_drill.py \
  --source var/paper_ledger.sqlite3 \
  --backup var/backups/paper_ledger-backup.sqlite3 \
  --restored var/restore-drill/paper_ledger-restored.sqlite3
```

The script refuses to overwrite either destination. It uses SQLite's online backup API (not a raw copy of the main DB file), checks SQLite integrity and foreign keys, opens each copy through the persistent paper broker so its hash chain and snapshot/audit-tail match are verified, compares every application table's row count, and emits SHA-256 hashes for the backup and restored files.

Keep backup and restore destinations on separate storage when conducting a real operational drill. This script verifies software-level backup and restore consistency; it does not establish data provenance, market performance, host endurance, or Level 3 certification.
