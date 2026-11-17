//! Shared domain logic for the BillFlow desktop application.
//!
//! This crate is the single source of truth for persistence, authentication,
//! billing math, reporting and analytics. It deliberately mirrors the business
//! rules implemented by the original Python backend so that the native app
//! produces byte-for-byte equivalent financial results.

pub mod audit;
pub mod auth;
pub mod db;
pub mod error;
pub mod models;
pub mod money;
pub mod repo;
pub mod services;

pub use error::{BillflowError, Result};

/// Small internal helpers shared by the repository and service modules.
pub(crate) mod util {
    use chrono::{SecondsFormat, Utc};
    use rusqlite::{Row, Rows};

    /// Current UTC time as an ISO-8601 string (`2026-11-18T09:31:00Z`).
    pub fn now_iso() -> String {
        Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true)
    }

    /// Current UTC calendar date (`YYYY-MM-DD`).
    pub fn today() -> String {
        Utc::now().format("%Y-%m-%d").to_string()
    }

    /// Read a nullable text column as a non-null `String` (NULL -> "").
    pub fn rs(row: &Row<'_>, name: &str) -> rusqlite::Result<String> {
        Ok(row.get::<_, Option<String>>(name)?.unwrap_or_default())
    }

    /// Read a nullable text column preserving NULL.
    pub fn ro(row: &Row<'_>, name: &str) -> rusqlite::Result<Option<String>> {
        row.get::<_, Option<String>>(name)
    }

    /// SQLite stores booleans as integers.
    pub fn rb(row: &Row<'_>, name: &str) -> rusqlite::Result<bool> {
        Ok(row.get::<_, i64>(name)? != 0)
    }

    /// Collect all rows produced by a statement using the supplied mapper.
    pub fn all<T, F>(mut rows: Rows<'_>, mut map: F) -> rusqlite::Result<Vec<T>>
    where
        F: FnMut(&Row<'_>) -> rusqlite::Result<T>,
    {
        let mut out = Vec::new();
        while let Some(row) = rows.next()? {
            out.push(map(row)?);
        }
        Ok(out)
    }

    pub fn uuid() -> String {
        uuid::Uuid::new_v4().to_string()
    }
}
