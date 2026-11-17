//! Append-only activity log.
//!
//! Logging is best-effort: a failure is isolated in a SAVEPOINT so it can never
//! break the business transaction that triggered it.

use rusqlite::{params, Connection};

use crate::util::{self, rs};

/// Resolve a stable display name for the actor of an action.
pub fn actor_name(conn: &Connection, user_id: Option<&str>) -> String {
    match user_id {
        Some(id) => conn
            .query_row("SELECT full_name FROM users WHERE id = ?1", params![id], |row| {
                rs(row, "full_name")
            })
            .unwrap_or_else(|_| "unknown".to_string()),
        None => "system".to_string(),
    }
}

/// Append an activity entry. Failures are swallowed by design.
pub fn log(
    conn: &Connection,
    business_id: &str,
    user_id: Option<&str>,
    action: &str,
    category: &str,
    reference: Option<&str>,
    details: Option<&str>,
) -> crate::error::Result<()> {
    let _ = conn.execute_batch("SAVEPOINT billflow_audit;");
    let result = (|| -> crate::error::Result<()> {
        let name = actor_name(conn, user_id);
        conn.execute(
            "INSERT INTO activity_logs \
             (id, business_id, user_id, user_name, action, category, reference, details, created_at) \
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
            params![
                util::uuid(),
                business_id,
                user_id,
                name,
                action,
                category,
                reference,
                details,
                util::now_iso(),
            ],
        )?;
        Ok(())
    })();
    if result.is_ok() {
        let _ = conn.execute_batch("RELEASE SAVEPOINT billflow_audit;");
    } else {
        let _ = conn.execute_batch(
            "ROLLBACK TO SAVEPOINT billflow_audit; RELEASE SAVEPOINT billflow_audit;",
        );
    }
    Ok(())
}
