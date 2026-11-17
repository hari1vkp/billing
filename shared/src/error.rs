use thiserror::Error;

/// Convenient result alias used by every public API in this crate.
pub type Result<T> = std::result::Result<T, BillflowError>;

/// All errors that can surface from the shared layer.
#[derive(Debug, Error)]
pub enum BillflowError {
    #[error("database error: {0}")]
    Db(#[from] rusqlite::Error),

    #[error("not found: {0}")]
    NotFound(String),

    #[error("validation error: {0}")]
    Validation(String),

    #[error("io error: {0}")]
    Io(#[from] std::io::Error),

    #[error("qr error: {0}")]
    Qr(String),

    #[error("pdf error: {0}")]
    Pdf(String),

    #[error("authentication error: {0}")]
    Auth(String),
}
