//! Password hashing and user authentication.
//!
//! Passwords are stored as `pbkdf2$<salt_hex>$<hash_hex>` using PBKDF2-HMAC-SHA256
//! with a random 32-byte salt and 210,000 iterations.

use pbkdf2::pbkdf2_hmac;
use rusqlite::{params, Connection};
use sha2::Sha256;

use crate::error::{BillflowError, Result};
use crate::models::{Role, User};
use crate::util::{self, rb, rs, ro};

const PBKDF2_ROUNDS: u32 = 210_000;
const SALT_BYTES: usize = 32;
const HASH_BYTES: usize = 32;

fn hex_encode(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for &b in bytes {
        out.push(HEX[(b >> 4) as usize] as char);
        out.push(HEX[(b & 0x0f) as usize] as char);
    }
    out
}

fn hex_decode(s: &str) -> Option<Vec<u8>> {
    if s.len() % 2 != 0 {
        return None;
    }
    let mut out = Vec::with_capacity(s.len() / 2);
    let bytes = s.as_bytes();
    for pair in bytes.chunks_exact(2) {
        let hi = (pair[0] as char).to_digit(16)?;
        let lo = (pair[1] as char).to_digit(16)?;
        out.push(((hi << 4) | lo) as u8);
    }
    Some(out)
}

fn derive(password: &str, salt: &[u8]) -> [u8; HASH_BYTES] {
    let mut out = [0u8; HASH_BYTES];
    pbkdf2_hmac::<Sha256>(password.as_bytes(), salt, PBKDF2_ROUNDS, &mut out);
    out
}

/// Hash a password with a fresh random salt.
pub fn hash_password(password: &str) -> Result<String> {
    if password.is_empty() {
        return Err(BillflowError::Auth("Password cannot be empty".into()));
    }
    // UUID v4 draws from a cryptographically secure OS source. Two values give
    // us a 32-byte salt without pulling in an extra RNG dependency.
    let mut salt = [0u8; SALT_BYTES];
    salt[..16].copy_from_slice(uuid::Uuid::new_v4().as_bytes());
    salt[16..].copy_from_slice(uuid::Uuid::new_v4().as_bytes());
    let hash = derive(password, &salt);
    Ok(format!("pbkdf2${}${}", hex_encode(&salt), hex_encode(&hash)))
}

/// Constant-time verification of a stored `pbkdf2$...` hash.
pub fn verify_password(password: &str, stored: &str) -> bool {
    let parts: Vec<&str> = stored.split('$').collect();
    if parts.len() != 3 || parts[0] != "pbkdf2" {
        return false;
    }
    let (Some(salt), Some(expected)) = (hex_decode(parts[1]), hex_decode(parts[2])) else {
        return false;
    };
    if expected.len() != HASH_BYTES {
        return false;
    }
    let actual = derive(password, &salt);
    let mut diff = 0u8;
    for (a, b) in actual.iter().zip(expected.iter()) {
        diff |= a ^ b;
    }
    diff == 0
}

pub(crate) fn user_from_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<User> {
    Ok(User {
        id: row.get("id")?,
        business_id: row.get("business_id")?,
        full_name: row.get("full_name")?,
        email: row.get("email")?,
        phone: ro(row, "phone")?,
        role: Role::from_str(&rs(row, "role")?),
        is_active: rb(row, "is_active")?,
        created_at: row.get("created_at")?,
    })
}

/// Validate credentials and return the active user.
pub fn authenticate(conn: &Connection, email: &str, password: &str) -> Result<User> {
    let mut stmt = conn.prepare(
        "SELECT * FROM users WHERE lower(email) = lower(?1) AND is_active = 1 LIMIT 1",
    )?;
    let found = stmt
        .query_map(params![email], user_from_row)?
        .next()
        .transpose()?;
    drop(stmt);

    let user = found.ok_or_else(|| BillflowError::Auth("Invalid email or password".into()))?;
    let stored: String = conn.query_row(
        "SELECT hashed_password FROM users WHERE id = ?1",
        params![user.id],
        |row| row.get(0),
    )?;
    if !verify_password(password, &stored) {
        return Err(BillflowError::Auth("Invalid email or password".into()));
    }
    let _ = conn.execute(
        "UPDATE users SET last_login_at = ?1 WHERE id = ?2",
        params![util::now_iso(), user.id],
    );
    Ok(user)
}

/// Create a user in a business with the supplied password.
pub fn create_user(
    conn: &Connection,
    business_id: &str,
    full_name: &str,
    email: &str,
    phone: Option<&str>,
    password: &str,
    role: Role,
) -> Result<User> {
    let exists: i64 = conn.query_row(
        "SELECT COUNT(*) FROM users WHERE lower(email) = lower(?1)",
        params![email],
        |row| row.get(0),
    )?;
    if exists > 0 {
        return Err(BillflowError::Validation(format!("Email {} is already in use", email)));
    }
    let user = User {
        id: util::uuid(),
        business_id: business_id.to_string(),
        full_name: full_name.to_string(),
        email: email.to_string(),
        phone: phone.map(str::to_string),
        role,
        is_active: true,
        created_at: util::now_iso(),
    };
    let now = &user.created_at;
    conn.execute(
        "INSERT INTO users (id, business_id, full_name, email, phone, hashed_password, \
         role, is_active, created_at, updated_at) \
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, 1, ?8, ?8)",
        params![
            user.id,
            user.business_id,
            user.full_name,
            user.email,
            user.phone,
            hash_password(password)?,
            user.role.as_str(),
            now,
        ],
    )?;
    Ok(user)
}

/// List all users belonging to a business.
pub fn list_users(conn: &Connection, business_id: &str) -> Result<Vec<User>> {
    let mut stmt = conn.prepare(
        "SELECT * FROM users WHERE business_id = ?1 ORDER BY created_at ASC, email ASC",
    )?;
    let rows = stmt.query(params![business_id])?;
    Ok(util::all(rows, user_from_row)?)
}

/// Enable or disable a user account.
pub fn set_user_active(conn: &Connection, user_id: &str, active: bool) -> Result<()> {
    let changed = conn.execute(
        "UPDATE users SET is_active = ?1, updated_at = ?2 WHERE id = ?3",
        params![active as i64, util::now_iso(), user_id],
    )?;
    if changed == 0 {
        return Err(BillflowError::NotFound(format!("User {} not found", user_id)));
    }
    Ok(())
}

/// Owners have unrestricted access; staff are limited.
pub fn is_owner(user: &User) -> bool {
    user.role == Role::Owner
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn password_hash_round_trips_and_rejects_wrong_password() {
        let stored = hash_password("Demo@1234").unwrap();
        assert!(stored.starts_with("pbkdf2$"));
        assert_eq!(stored.split('$').count(), 3);
        assert!(verify_password("Demo@1234", &stored));
        assert!(!verify_password("wrong", &stored));
        assert!(!verify_password("Demo@1234", "not-a-hash"));
    }
}
